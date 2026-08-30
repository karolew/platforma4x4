"""Konfiguracja jednego PX1122R (Base albo Rover) przez wspolny Px1122rBus.

Uzywane WYLACZNIE poza normalna petla RtkGnssProvider - przy starcie albo na
zadanie. Kody komend (message ID) wg SkyTraq AN0039 - do uzupelnienia.
"""
from __future__ import annotations

import asyncio
import struct

from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target
from rover.services.navigation.gnss.px1122r_protocol import START, FrameError, decode_message, encode_message

_ACK = 0x83
_NACK = 0x84
_RATE_RESPONSE = 0x86

_SERIAL_PORT_MSG = 0x05  # standardowa komenda SkyTraq "Configure Serial Port" (nie w AN0039 tego modulu)
_BAUD_RATE_IDS = {4800: 0, 9600: 1, 19200: 2, 38400: 3, 57600: 4, 115200: 5, 230400: 6, 460800: 7, 921600: 8}

_SYSTEM_RESTART_MSG = 0x01  # standardowa komenda SkyTraq "System Restart" (bazowy protokol calej rodziny SkyTraq, nie w AN0039 tego modulu - wymaga potwierdzenia na sprzecie)
RESTART_HOT = 0
RESTART_WARM = 1
RESTART_COLD = 2
RESTART_TEST = 3  # GPS-only test mode - formalnie tryb startu, nie "restart"

_RTK_MODE_MSG = 0x6A  # AN0028 (SkyTraq Venus 8) "Configure RTK Mode and Operational Function" - nieudokumentowane dla PX1122R, do potwierdzenia
_RTK_MODE_CONFIGURE_SID = 0x06
_RTK_MODE_QUERY_SID = 0x07
_RTK_MODE_RESPONSE_SID = 0x83  # kolizja z _ACK generycznym - bez znaczenia, to sub-id wewnatrz body 0x6A, nie top-level msg_id

RTK_MODE_ROVER = 0
RTK_MODE_BASE = 1
RTK_MODE_PRECISE_KINEMATIC_BASE = 2

RTK_ROVER_FUNC_NORMAL = 0
RTK_ROVER_FUNC_FLOAT = 1
RTK_ROVER_FUNC_MOVING_BASE = 2

RTK_BASE_FUNC_KINEMATIC = 0
RTK_BASE_FUNC_SURVEY = 1
RTK_BASE_FUNC_STATIC = 2

# Sub-komendy wewnatrz 0x6A (body[0]) do konfiguracji baudrate WEWNETRZNYCH portow
# szeregowych miedzy dwoma modulami PX1122R (nie mylic z _SERIAL_PORT_MSG=0x05, ktore
# ustawia UART hosta). Potwierdzone bajt-w-bajt w komendy_z_gnss_viewer.txt (RTK 5/6),
# query SID dla base-serial potwierdzone (RTK 3); query SID dla slave-serial
# WYWNIOSKOWANY z konwencji "query = configure_sid + 1" (potwierdzonej niezaleznie na
# parach 0x06/0x07 i 0x13/0x14) - oryginalna komenda RTK 2 w pliku byla uszkodzona
# (brak `\x` przed hex w zrzucie), wiec do potwierdzenia na sprzecie.
#
# WAZNE - zakres stosowania (wg NS-HP-GN2-User-Guide.pdf, cytat 2026-08-26): przy
# advanced moving base >=4Hz trzeba osobno skonfigurowac na 230400: (1) glowny UART
# TXD Base [_SERIAL_PORT_MSG=0x05, NIE tutaj], (2) "receiver C moving base rover RXD2
# UART" = SLAVE SERIAL PONIZEJ - dotyczy WYLACZNIE Rovera (target="rover"), Base nie ma
# tu roli, (3) "receiver B & C I2C mapped UART" = BASE SERIAL PONIZEJ - trzeba wyslac
# do OBU jednostek osobno (target="base" I target="rover"), bo obie strony linku musza
# miec zgodny baudrate.
_SLAVE_SERIAL_BAUD_SID = 0x0C  # tylko Rover - patrz uwaga wyzej
_SLAVE_SERIAL_BAUD_QUERY_SID = 0x0D  # niepotwierdzone na sprzecie, patrz wyzej
_BASE_SERIAL_BAUD_SID = 0x13  # ustawic na OBU jednostkach - patrz uwaga wyzej
_BASE_SERIAL_BAUD_QUERY_SID = 0x14

# Standardowe komendy SkyTraq (top-level msg_id, inna przestrzen niz sub-SID w 0x6A
# powyzej - kolizja numeryczna 0x0C jest przypadkowa i nieszkodliwa). Potwierdzone
# bajt-w-bajt w komendy_z_gnss_viewer.txt (OGOLNE 3/6).
_POWER_MODE_QUERY_MSG = 0x15
_POWER_MODE_CONFIGURE_MSG = 0x0C
POWER_MODE_NORMAL = 0
POWER_MODE_SAVE = 1

# OGOLNE 1 w komendy_z_gnss_viewer.txt: GNSS Viewer wysyla te dwie komendy razem dla
# ekranu "SW info". Drugi bajt body w obu przypadkach zaobserwowany, znaczenie
# nieustalone (prawdopodobnie typ/wersja) - odtwarzane 1:1, bez interpretacji.
_SW_VERSION_MSG = 0x02
_SW_VERSION_BODY = bytes([0x01])
_SW_CRC_MSG = 0x64
_SW_CRC_BODY = bytes([0x7D])


class Px1122rConfigClient:
    def __init__(self, bus: Px1122rBus, target: Target) -> None:
        self._bus = bus
        self._target = target
        self._lock = asyncio.Lock()
        self._buf = bytearray()

    async def _read_frame(self) -> bytes:
        """Zwraca jedna pelna ramke START..END, pomijajac NMEA/szum przed START.

        Modul strumieniuje NMEA rownolegle z odpowiedziami binarnymi na tym samym
        UART, wiec bufor moze zawierac dowolna ilosc smieci przed nastepna ramka
        - a takze wiecej niz jedna gotowa ramke naraz (patrz `_query`).
        """
        while True:
            start = self._buf.find(START)
            if start == -1:
                if len(self._buf) > 1:
                    del self._buf[:-1]  # zachowaj ostatni bajt - moglby byc poczatkiem START
                chunk = await self._bus.read(256)
                if not chunk:
                    raise FrameError("timeout - brak ramki od modulu")
                self._buf += chunk
                continue
            if len(self._buf) < start + 4:
                chunk = await self._bus.read(256)
                if not chunk:
                    raise FrameError("timeout - niekompletny naglowek ramki")
                self._buf += chunk
                continue
            length = int.from_bytes(self._buf[start + 2 : start + 4], "big")
            end = start + 4 + length + 1 + 2  # naglowek + payload + checksum + END
            if len(self._buf) < end:
                chunk = await self._bus.read(256)
                if not chunk:
                    raise FrameError("timeout - niekompletna ramka")
                self._buf += chunk
                continue
            frame = bytes(self._buf[start:end])
            del self._buf[:end]
            return frame

    async def _request(self, msg_id: int, body: bytes = b"") -> tuple[int, bytes]:
        """Dla komend ustawiajacych - modul odpowiada jedna ramka ACK/NACK."""
        async with self._lock:
            await self._bus.select(self._target)
            await self._bus.write(encode_message(msg_id, body))
            return decode_message(await self._read_frame())

    async def _query(self, msg_id: int, body: bytes = b"") -> tuple[int, bytes]:
        """Dla zapytan - modul czasem odsyla najpierw ACK dla samej komendy a
        potem osobna ramke z danymi, a czasem odpowiada dana ramka bezposrednio
        (oba warianty zaobserwowane na sprzecie) - wiec ACK jest pomijany, a
        zwracana jest pierwsza NIE-ACK ramka."""
        async with self._lock:
            await self._bus.select(self._target)
            await self._bus.write(encode_message(msg_id, body))
            while True:
                resp_id, resp_body = decode_message(await self._read_frame())
                if resp_id == _NACK:
                    raise RuntimeError(f"PX1122R NACK: {resp_body!r}")
                if resp_id == _ACK:
                    continue
                return resp_id, resp_body

    def _check_ack(self, msg_id: int, body: bytes) -> None:
        if msg_id == _NACK:
            raise RuntimeError(f"PX1122R NACK: {body!r}")
        if msg_id != _ACK:
            raise RuntimeError(f"nieoczekiwana odpowiedz (ID=0x{msg_id:02X}): {body!r}")

    async def get_output_rate(self) -> int:
        msg_id, body = await self._query(0x10)  # AN0039: query position update rate
        if msg_id != _RATE_RESPONSE:
            raise RuntimeError(f"nieoczekiwana odpowiedz (ID=0x{msg_id:02X}): {body!r}")
        return body[0]

    async def set_output_rate(self, hz: int, save_to_flash: bool = True) -> None:
        # AN0039: rate_byte = wartosc Hz wprost (potwierdzone: 0x01/0x05/0x0A dla 1/5/10Hz)
        msg_id, body = await self._request(0x0E, bytes([hz, int(save_to_flash)]))
        self._check_ack(msg_id, body)

    # Baseline jako samodzielna komenda (0x64/0x21, 0x6E/0x01|0x02) dostawala jednolity
    # NACK na sprzecie 2026-07-27 niezaleznie od formatu body - patrz get_baseline_m
    # usuniete tego samego dnia. Znaleziono jednak w AN0028 (SkyTraq Venus 8, dokument
    # dla innego chipsetu niz PX1122R - do potwierdzenia) realna komende laczaca tryb
    # RTK z wymuszona dlugoscia baseline: configure_rtk_mode() nizej, pole
    # baseline_length_m, uzywane gdy Rover ma operational_function=RTK_ROVER_FUNC_MOVING_BASE.

    async def configure_rtk_mode(
        self,
        mode: int,
        operational_function: int,
        survey_length_s: int = 60,
        standard_deviation_m: int = 30,
        latitude_deg: float = 0.0,
        longitude_deg: float = 0.0,
        altitude_m: float = 0.0,
        baseline_length_m: float = 0.0,
        save_to_flash: bool = True,
    ) -> None:
        """SkyTraq 'Configure RTK Mode and Operational Function' (0x6A/0x06, wg AN0028
        dla Venus 8 - nieudokumentowane dla PX1122R, wymaga potwierdzenia na sprzecie).
        Jedna komenda ustawia jednoczesnie tryb RTK (RTK_MODE_ROVER/BASE/PRECISE_
        KINEMATIC_BASE), funkcje operacyjna (dla Rovera: NORMAL/FLOAT/MOVING_BASE, dla
        Base: KINEMATIC/SURVEY/STATIC) oraz - gdy Rover ma funkcje MOVING_BASE -
        wymuszona dlugosc baseline (uzyj 0.0 jesli nieznana/plywajaca).

        survey_length_s=60/standard_deviation_m=30 domyslnie (zamiast 0/0 sprzed
        2026-08-26) - dokladnie to wysyla GNSS Viewer dla KAZDEGO trybu (advanced-base
        I rover), potwierdzone bajt-w-bajt w komendy_z_gnss_viewer.txt. System dziala
        (heading OK) skonfigurowany przez GNSS Viewer, nie dzialal przez ten klient ze
        starymi domyslnymi 0/0 - te pola byly glownym podejrzanym, do potwierdzenia
        na sprzecie czy realnie to byla przyczyna."""
        body = bytes([_RTK_MODE_CONFIGURE_SID, mode, operational_function])
        body += survey_length_s.to_bytes(4, "big")
        body += standard_deviation_m.to_bytes(4, "big")
        body += struct.pack(">d", latitude_deg)
        body += struct.pack(">d", longitude_deg)
        body += struct.pack(">f", altitude_m)
        body += struct.pack(">f", baseline_length_m)
        body += bytes([int(save_to_flash)])
        msg_id, resp_body = await self._request(_RTK_MODE_MSG, body)
        self._check_ack(msg_id, resp_body)

    async def query_rtk_mode(self) -> tuple[int, int, float]:
        """Zwraca (rtk_mode, operational_function, baseline_length_m) - 0x6A/0x07 query,
        odpowiedz 0x6A/0x83."""
        _, body = await self._query(_RTK_MODE_MSG, bytes([_RTK_MODE_QUERY_SID]))
        if body[0] != _RTK_MODE_RESPONSE_SID:
            raise RuntimeError(f"nieoczekiwana odpowiedz (SID=0x{body[0]:02X}): {body!r}")
        # Uklad pol identyczny jak w tele configure_rtk_mode (bez koncowego save_to_flash),
        # potwierdzone na sprzecie 2026-07-27: baseline_length_m na bajtach 31-34 (nie
        # ostatnie 4B - za body jeszcze 5 nieznanych bajtow, prawdopodobnie baseline_course_deg + rezerwa).
        (
            _sid,
            mode,
            operational_function,
            _survey_length_s,
            _standard_deviation_m,
            _latitude_deg,
            _longitude_deg,
            _altitude_m,
            baseline_length_m,
        ) = struct.unpack(">BBBIIddff", body[:35])
        return mode, operational_function, baseline_length_m

    async def set_baudrate(self, baud: int, save_to_flash: bool = False) -> None:
        """SkyTraq 'Configure Serial Port' (0x05) - standardowa komenda uzywana w wielu
        modulach SkyTraq, nieudokumentowana w dostepnym AN0039 (Raw Measurement Data
        Extension) dla tego modulu, wiec wymaga potwierdzenia na sprzecie. Po ACK modul
        natychmiast przelacza UART na nowy baudrate - trzeba takze przelaczyc/otworzyc
        polaczenie hosta na `baud`, inaczej kolejne odpowiedzi beda nieczytelne.
        `save_to_flash=False` domyslnie: restart/reset zasilania przywraca poprzedni
        baudrate, jesli cos pojdzie nie tak."""
        if baud not in _BAUD_RATE_IDS:
            raise ValueError(f"nieobslugiwany baudrate: {baud}")
        body = bytes([0x00, _BAUD_RATE_IDS[baud], int(save_to_flash)])
        msg_id, resp_body = await self._request(_SERIAL_PORT_MSG, body)
        self._check_ack(msg_id, resp_body)

    async def restart(self, mode: int = RESTART_HOT) -> None:
        """SkyTraq 'System Restart' (0x01) - standardowa komenda z bazowego binarnego
        protokolu SkyTraq (cala rodzina chipsetow), nieudokumentowana w dostepnym
        AN0039 dla PX1122R - wymaga potwierdzenia na sprzecie (analogicznie do
        set_baudrate()/configure_rtk_mode() w tym pliku).
        RESTART_HOT: uzywa zapisanych efemeryd/almanachu/pozycji/czasu bez zmian.
        RESTART_WARM: odrzuca efemerydy, zachowuje almanach/przyblizona pozycje/czas.
        RESTART_COLD: pelny cold start - odrzuca efemerydy+almanach+pozycje+czas,
        najdluzszy czas do pierwszego fixa.
        Wysyla wylacznie bajt trybu, bez opcjonalnej podpowiedzi UTC/pozycji
        przyspieszajacej COLD start - dokladny uklad tych dodatkowych pol nie jest
        pewny bez zrodlowego dokumentu, do uzupelnienia jesli modul zwroci NACK
        oczekujac dluzszego body."""
        msg_id, resp_body = await self._request(_SYSTEM_RESTART_MSG, bytes([mode]))
        self._check_ack(msg_id, resp_body)

    async def restart_hot(self) -> None:
        await self.restart(RESTART_HOT)

    async def restart_warm(self) -> None:
        await self.restart(RESTART_WARM)

    async def restart_cold(self) -> None:
        await self.restart(RESTART_COLD)

    async def configure_as_base(self, save_to_flash: bool = True) -> None:
        """Precisely Kinematic Mode Base (datasheet 'Advanced Moving Base') - odbiera
        RTCM/NTRIP od hosta, przekazuje korekty do Rovera bezposrednim przewodem
        (poza RPi). Uzywa 0x6A, patrz configure_rtk_mode() (w tym jego domyslne
        survey_length_s/standard_deviation_m, dopasowane do GNSS Viewer)."""
        await self.configure_rtk_mode(RTK_MODE_PRECISE_KINEMATIC_BASE, RTK_BASE_FUNC_KINEMATIC, save_to_flash=save_to_flash)

    async def configure_as_rover(self, baseline_length_m: float, save_to_flash: bool = True) -> None:
        """Moving Base Mode Rover (datasheet 'Advanced Moving Base') - liczy wektor
        baseline wzgledem Base. `baseline_length_m` to znana/oczekiwana dlugosc anteny
        do anteny, uzywana przez RTK-engine do przyspieszenia fixowania ambiguity.
        Uzywa 0x6A, patrz configure_rtk_mode() (w tym jego domyslne survey_length_s/
        standard_deviation_m, dopasowane do GNSS Viewer - wysylane nawet dla Rovera,
        gdzie formalnie nie maja znaczenia)."""
        await self.configure_rtk_mode(
            RTK_MODE_ROVER, RTK_ROVER_FUNC_MOVING_BASE, baseline_length_m=baseline_length_m, save_to_flash=save_to_flash
        )

    async def get_slave_serial_baud(self) -> bytes:
        """Query 'RTK slave serial port baud rate' (0x6A/0x0D, SID wywnioskowany - patrz
        komentarz przy _SLAVE_SERIAL_BAUD_QUERY_SID). Zwraca surowe body odpowiedzi -
        uklad pol niepotwierdzony na sprzecie (plik zawiera tylko komendy wychodzace)."""
        _, body = await self._query(_RTK_MODE_MSG, bytes([_SLAVE_SERIAL_BAUD_QUERY_SID]))
        return body

    async def get_base_serial_baud(self) -> bytes:
        """Query 'RTK precisely kinematic base serial port baud rate' (0x6A/0x14) -
        SID potwierdzony w komendy_z_gnss_viewer.txt (RTK 3). Zwraca surowe body
        odpowiedzi - uklad pol niepotwierdzony na sprzecie."""
        _, body = await self._query(_RTK_MODE_MSG, bytes([_BASE_SERIAL_BAUD_QUERY_SID]))
        return body

    async def set_slave_serial_baud(self, baud: int, save_to_flash: bool = True) -> None:
        """Configure 'RTK slave serial port baud rate' (0x6A/0x0C) - potwierdzone
        bajt-w-bajt w komendy_z_gnss_viewer.txt (RTK 5). To port MIEDZY dwoma modulami
        PX1122R, nie UART hosta (patrz set_baudrate())."""
        if baud not in _BAUD_RATE_IDS:
            raise ValueError(f"nieobslugiwany baudrate: {baud}")
        body = bytes([_SLAVE_SERIAL_BAUD_SID, _BAUD_RATE_IDS[baud], int(save_to_flash)])
        msg_id, resp_body = await self._request(_RTK_MODE_MSG, body)
        self._check_ack(msg_id, resp_body)

    async def set_base_serial_baud(self, baud: int, save_to_flash: bool = True) -> None:
        """Configure 'RTK precisely kinematic base serial port baud rate' (0x6A/0x13) -
        potwierdzone bajt-w-bajt w komendy_z_gnss_viewer.txt (RTK 6)."""
        if baud not in _BAUD_RATE_IDS:
            raise ValueError(f"nieobslugiwany baudrate: {baud}")
        body = bytes([_BASE_SERIAL_BAUD_SID, _BAUD_RATE_IDS[baud], int(save_to_flash)])
        msg_id, resp_body = await self._request(_RTK_MODE_MSG, body)
        self._check_ack(msg_id, resp_body)

    async def get_power_mode(self) -> bytes:
        """Query power mode (0x15, brak body) - potwierdzone w komendy_z_gnss_viewer.txt
        (OGOLNE 3). Zwraca surowe body odpowiedzi - uklad pol niepotwierdzony na
        sprzecie."""
        _, body = await self._query(_POWER_MODE_QUERY_MSG)
        return body

    async def set_power_mode(self, mode: int, save_to_flash: bool = True) -> None:
        """Configure power mode (0x0C top-level, body=[mode, save]) - potwierdzone
        bajt-w-bajt w komendy_z_gnss_viewer.txt (OGOLNE 6). Uzyj POWER_MODE_NORMAL/
        POWER_MODE_SAVE."""
        msg_id, resp_body = await self._request(_POWER_MODE_CONFIGURE_MSG, bytes([mode, int(save_to_flash)]))
        self._check_ack(msg_id, resp_body)

    async def get_sw(self) -> tuple[bytes, bytes]:
        """Odtwarza 1:1 dwie komendy wysylane przez GNSS Viewer dla ekranu 'SW info'
        (komendy_z_gnss_viewer.txt OGOLNE 1): 0x02 (Query Software Version, standardowa
        SkyTraq) i 0x64 (prawdopodobnie Query Software CRC). Zwraca surowe body obu
        odpowiedzi bez interpretacji - znaczenie parametrow/odpowiedzi nieustalone."""
        _, version_body = await self._query(_SW_VERSION_MSG, _SW_VERSION_BODY)
        _, crc_body = await self._query(_SW_CRC_MSG, _SW_CRC_BODY)
        return version_body, crc_body
