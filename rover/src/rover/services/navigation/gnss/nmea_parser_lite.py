from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger("nmea_parser_lite")

_KNOTS_TO_KMH = 1.852

# GGA field 6 - GPS quality indicator (0-8), indeks = wartosc pola
QUALITY = (
    "Fix Unavailable",
    "SPS Fix",
    "DGPS Fix",
    "PPS Fix",
    "RTK Fix",
    "RTK Float",
    "Estimated (dead reckoning) Mode",
    "Manual Input Mode",
    "Simulator Mode",
)

# Mode indicator (RMC/VTG/GLL/PSTI030) i Mode (THS) / baseline mode (PSTI032/035)
MODES = {
    "A": "Autonomous Mode",
    "D": "Differential Mode",
    "E": "Estimated (dead reckoning) Mode",
    "M": "Manual Input Mode",
    "S": "Simulator Mode",
    "N": "Data Not Valid",
    "V": "Data Not Valid",
    "R": "RTK Fix",
    "F": "RTK Float",
    "P": "Precise",
}


def _checksum_ok(raw: str) -> bool:
    if not raw.startswith("$") or "*" not in raw:
        return False
    body, _, chk = raw[1:].partition("*")
    chk = chk.strip()
    if len(chk) < 2:
        return False
    calc = 0
    for c in body:
        calc ^= ord(c)
    try:
        return calc == int(chk[:2], 16)
    except ValueError:
        return False


def _split_head(raw: str) -> tuple[str, list[str]]:
    body = raw[1:].split("*", 1)[0]
    head, *fields = body.split(",")
    return head, fields


def _to_float(s: str) -> Optional[float]:
    return float(s) if s else None


def _to_int(s: str) -> Optional[int]:
    return int(s) if s else None


def _nmea_coord(value: str, hemi: str, decimal: bool) -> Optional[float]:
    if not value or not hemi:
        return None
    sign = -1.0 if hemi in ("S", "W") else 1.0
    if not decimal:
        return sign * float(value)  # dddmm.mmmmmmm - format natywny NMEA
    dot = value.index(".")
    deg_len = dot - 2
    deg = float(value[:deg_len])
    minutes = float(value[deg_len:])
    return sign * (deg + minutes / 60.0)


def _format_time(raw_hhmmss: str) -> str:
    # "033010.000" / "121959.0000003" -> "03:30:10.000" / "12:19:59.0000003"
    whole, _, frac = raw_hhmmss.partition(".")
    if len(whole) < 6:
        return raw_hhmmss
    text = f"{whole[0:2]}:{whole[2:4]}:{whole[4:6]}"
    return f"{text}.{frac}" if frac else text


def _format_date(raw_ddmmyy: str) -> str:
    # "111219" -> "2019-12-11" (zaklada wiek 20xx, NMEA rok jest 2-cyfrowy)
    if len(raw_ddmmyy) != 6:
        return raw_ddmmyy
    dd, mm, yy = raw_ddmmyy[0:2], raw_ddmmyy[2:4], raw_ddmmyy[4:6]
    return f"20{yy}-{mm}-{dd}"


@dataclass(frozen=True)
class SatelliteInfo:
    talker: str  # GP/GL/GA/GB - konstelacja
    prn: int
    elevation: Optional[int]
    azimuth: Optional[int]
    cnr: Optional[int]


@dataclass
class NavigationState:
    epoch_utc: Optional[str] = None
    epoch_date: Optional[str] = None

    fix_valid: bool = False
    fix_quality: int = 0
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt: Optional[float] = None
    num_sats: int = 0
    hdop: Optional[float] = None
    pdop: Optional[float] = None
    vdop: Optional[float] = None

    speed: Optional[float] = None  # jednostka wg konfiguracji: knots (raw) / km/h (iso8601)
    course_deg: Optional[float] = None
    vel_e: Optional[float] = None
    vel_n: Optional[float] = None
    vel_u: Optional[float] = None

    heading_deg: Optional[float] = None
    heading_mode: Optional[str] = None

    nav_mode: Optional[str] = None
    rtk_age: Optional[float] = None
    rtk_ratio: Optional[float] = None

    # PSTI,032 - baseline rover <-> zewnetrzna stacja bazowa
    baseline_e_032: Optional[float] = None
    baseline_n_032: Optional[float] = None
    baseline_u_032: Optional[float] = None
    baseline_len_032: Optional[float] = None
    baseline_mode_032: Optional[str] = None

    # PSTI,035 - baseline wlasnych anten AMB (heading), NIE zasila heading_deg
    baseline_e_035: Optional[float] = None
    baseline_n_035: Optional[float] = None
    baseline_u_035: Optional[float] = None
    baseline_len_035: Optional[float] = None
    baseline_mode_035: Optional[str] = None

    # niekrytyczne, tylko gdy track_satellites=True; krotka - nigdy nie mutowac w miejscu
    satellites: tuple[SatelliteInfo, ...] = ()

    @property
    def quality_str(self) -> str:
        return QUALITY[self.fix_quality] if 0 <= self.fix_quality < len(QUALITY) else "Unknown"

    @property
    def nav_mode_str(self) -> Optional[str]:
        return MODES.get(self.nav_mode)

    @property
    def heading_mode_str(self) -> Optional[str]:
        return MODES.get(self.heading_mode)

    @property
    def baseline_mode_032_str(self) -> Optional[str]:
        return MODES.get(self.baseline_mode_032)

    @property
    def baseline_mode_035_str(self) -> Optional[str]:
        return MODES.get(self.baseline_mode_035)


class NMEAParser:
    """Parser bez wsparcia UART/threading - zasilany wylacznie przez feed_line().

    Do uzycia w kontekstach, gdzie IO/watchdog/wspoldzielenie portu jest
    zarzadzane przez wywolujacego (np. replay z pliku, testy, integracja
    z wlasna petla asyncio, wspoldzielony UART z komendami/ACK).
    """

    def __init__(
        self,
        unit_format: str = "iso8601",
        coord_format: str = "raw",
        track_satellites: bool = False,
    ) -> None:
        if unit_format not in ("iso8601", "raw"):
            raise ValueError("unit_format must be 'iso8601' or 'raw'")
        if coord_format not in ("raw", "decimal_degrees"):
            raise ValueError("coord_format must be 'raw' or 'decimal_degrees'")
        self._iso_units = unit_format == "iso8601"
        self._decimal_coords = coord_format == "decimal_degrees"
        self._track_satellites = track_satellites
        self._gsv_staging: dict[str, list[SatelliteInfo]] = {}

        self._state = NavigationState()

        self._handlers: dict[str, Callable[[list[str]], None]] = {
            "GGA": self._parse_gga,
            "GLL": self._parse_gll,
            "GSA": self._parse_gsa,
            "GSV": self._parse_gsv,
            "RMC": self._parse_rmc,
            "VTG": self._parse_vtg,
            "ZDA": self._parse_zda,
            "THS": self._parse_ths,
        }
        self._psti_handlers: dict[str, Callable[[list[str]], None]] = {
            "005": self._parse_psti_005,
            "030": self._parse_psti_030,
            "032": self._parse_psti_032,
            "033": self._parse_psti_033,
            "035": self._parse_psti_035,
        }

    def get_state(self) -> NavigationState:
        return copy.copy(self._state)

    # --- parsing -----------------------------------------------------------

    def feed_line(self, raw: str) -> bool:
        raw = raw.strip()
        if not raw or not _checksum_ok(raw):
            log.debug("bad checksum or malformed line: %r", raw)
            return False
        head, fields = _split_head(raw)
        if head.startswith("P"):
            return self._dispatch_proprietary(head, fields)
        return self._dispatch_standard(head, fields)

    def _dispatch_standard(self, head: str, fields: list[str]) -> bool:
        talker, msg_id = head[:2], head[2:]
        handler = self._handlers.get(msg_id)
        if handler is None:
            log.debug("unsupported sentence: %s", msg_id)
            return False
        if msg_id == "GSV":
            handler(talker, fields)  # GSV jest per-konstelacja, potrzebny talker
        else:
            handler(fields)
        return True

    def _dispatch_proprietary(self, head: str, fields: list[str]) -> bool:
        if head[1:] != "STI" or not fields:
            log.debug("unsupported proprietary sentence: %s", head)
            return False
        sub_id, *rest = fields
        handler = self._psti_handlers.get(sub_id)
        if handler is None:
            log.debug("unsupported PSTI sub-id: %s", sub_id)
            return False
        handler(rest)
        return True

    def _set_epoch(self, utc: Optional[str], date: Optional[str] = None) -> None:
        if utc:
            self._state.epoch_utc = _format_time(utc) if self._iso_units else utc
        if date:
            self._state.epoch_date = _format_date(date) if self._iso_units else date

    def _parse_coord(self, value: str, hemi: str) -> Optional[float]:
        return _nmea_coord(value, hemi, self._decimal_coords)

    # --- standardowe sentence NMEA ------------------------------------------

    def _parse_gga(self, f: list[str]) -> None:
        if len(f) < 9:
            return
        self._set_epoch(f[0])
        self._state.lat = self._parse_coord(f[1], f[2])
        self._state.lon = self._parse_coord(f[3], f[4])
        self._state.fix_quality = _to_int(f[5]) or 0
        self._state.fix_valid = self._state.fix_quality > 0
        self._state.num_sats = _to_int(f[6]) or 0
        self._state.hdop = _to_float(f[7])
        self._state.alt = _to_float(f[8])

    def _parse_gll(self, f: list[str]) -> None:
        if len(f) < 6:
            return
        self._set_epoch(f[4])
        if f[5] == "A":
            self._state.lat = self._parse_coord(f[0], f[1])
            self._state.lon = self._parse_coord(f[2], f[3])

    def _parse_gsa(self, f: list[str]) -> None:
        if len(f) < 17:
            return
        self._state.pdop = _to_float(f[14])
        self._state.hdop = _to_float(f[15])
        self._state.vdop = _to_float(f[16])

    def _parse_gsv(self, talker: str, f: list[str]) -> None:
        if not self._track_satellites or len(f) < 3:
            return
        total_msgs = _to_int(f[0]) or 1
        msg_num = _to_int(f[1]) or 1
        body = f[3:]
        if len(body) % 4 == 1:
            body = body[:-1]  # ostatnie pole to signal ID, nieuzywane

        sats: list[SatelliteInfo] = []
        for i in range(0, len(body), 4):
            group = body[i : i + 4]
            if len(group) < 4:
                break
            prn = _to_int(group[0])
            if prn is None:
                continue
            sats.append(SatelliteInfo(talker, prn, _to_int(group[1]), _to_int(group[2]), _to_int(group[3])))

        staged = self._gsv_staging.setdefault(talker, [])
        if msg_num == 1:
            staged.clear()
        staged.extend(sats)

        if msg_num >= total_msgs:
            others = tuple(s for s in self._state.satellites if s.talker != talker)
            self._state.satellites = others + tuple(staged)  # podmiana calej krotki, nie mutacja
            staged.clear()

    def _parse_rmc(self, f: list[str]) -> None:
        if len(f) < 12:
            return
        self._set_epoch(f[0], f[8])
        self._state.fix_valid = f[1] == "A"
        self._state.lat = self._parse_coord(f[2], f[3])
        self._state.lon = self._parse_coord(f[4], f[5])
        speed_kn = _to_float(f[6])
        self._state.speed = speed_kn * _KNOTS_TO_KMH if (self._iso_units and speed_kn is not None) else speed_kn
        self._state.course_deg = _to_float(f[7])
        self._state.nav_mode = f[11] or None

    def _parse_vtg(self, f: list[str]) -> None:
        if len(f) < 9:
            return
        self._state.course_deg = _to_float(f[0])
        # VTG niesie oba warianty natywnie (knots i km/h) - bez przeliczania
        self._state.speed = _to_float(f[6]) if self._iso_units else _to_float(f[4])

    def _parse_zda(self, f: list[str]) -> None:
        if len(f) < 4:
            return
        day, month, year = f[1], f[2], f[3]
        date_ddmmyy = f"{day.zfill(2)}{month.zfill(2)}{year[-2:]}" if day and month and year else None
        self._set_epoch(f[0], date_ddmmyy)

    def _parse_ths(self, f: list[str]) -> None:
        if len(f) < 2:
            return
        # brak wlasnego UTC w THS - podpina sie pod aktualny epoch_utc
        self._state.heading_deg = _to_float(f[0])
        self._state.heading_mode = f[1] or None

    # --- proprietary SkyTraq $PSTI ------------------------------------------

    def _parse_psti_005(self, f: list[str]) -> None:
        if len(f) < 1:
            return
        self._set_epoch(f[0])

    def _parse_psti_030(self, f: list[str]) -> None:
        if len(f) < 14:
            return
        self._set_epoch(f[0], f[10])
        self._state.fix_valid = f[1] == "A"
        self._state.lat = self._parse_coord(f[2], f[3])
        self._state.lon = self._parse_coord(f[4], f[5])
        self._state.alt = _to_float(f[6])
        self._state.vel_e = _to_float(f[7])
        self._state.vel_n = _to_float(f[8])
        self._state.vel_u = _to_float(f[9])
        self._state.nav_mode = f[11] or None
        self._state.rtk_age = _to_float(f[12])
        self._state.rtk_ratio = _to_float(f[13])

    def _parse_psti_032(self, f: list[str]) -> None:
        # baseline rover <-> zewnetrzna stacja bazowa (nie mylic z PSTI,035)
        if len(f) < 8:
            return
        self._set_epoch(f[0], f[1])
        self._state.baseline_mode_032 = f[3] or None
        self._state.baseline_e_032 = _to_float(f[4])
        self._state.baseline_n_032 = _to_float(f[5])
        self._state.baseline_u_032 = _to_float(f[6])
        self._state.baseline_len_032 = _to_float(f[7])

    def _parse_psti_035(self, f: list[str]) -> None:
        # baseline wlasnych anten AMB (rover moving base) - tylko diagnostyka,
        # heading bierzemy wylacznie z THS
        if len(f) < 8:
            return
        self._set_epoch(f[0], f[1])
        self._state.baseline_mode_035 = f[3] or None
        self._state.baseline_e_035 = _to_float(f[4])
        self._state.baseline_n_035 = _to_float(f[5])
        self._state.baseline_u_035 = _to_float(f[6])
        self._state.baseline_len_035 = _to_float(f[7])

    def _parse_psti_033(self, f: list[str]) -> None:
        if len(f) < 2:
            return
        self._set_epoch(f[0], f[1])  # status per-konstelacja pomijany (uproszczenie)


def _with_checksum(body: str) -> str:
    calc = 0
    for c in body:
        calc ^= ord(c)
    return f"${body}*{calc:02X}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    sample_lines = [
        "$GPGGA,033010.000,2447.0895508,N,12100.5234656,E,4,12,0.7,94.615,M,19.600,M,,0000*66",
        "$GNGLL,2447.0895508,N,12100.5234656,E,033010.000,A,D*48",
        "$GNGSA,A,3,05,12,13,15,20,21,24,193,,,,,1.2,0.7,1.0,1*08",
        "$GPGSV,3,1,10,24,83,125,48,193,66,057,44,21,53,277,45,15,43,034,47,1*58",
        "$GPGSV,3,2,10,20,40,325,43,05,16,113,40,13,15,050,39,12,14,146,42,1*6E",
        "$GPGSV,3,3,10,10,13,314,,32,06,261,,1*62",
        "$GNRMC,033010.000,A,2447.0895508,N,12100.5234656,E,000.0,000.0,111219,,,R,V*18",
        "$GNVTG,000.0,T,,M,000.0,N,000.0,K,D*16",
        "$GNZDA,033010.000,11,12,2019,00,00*40",
        _with_checksum("GNTHS,121.15,A"),
        "$PSTI,005,121959.0000003,20,07,2020,,,,,*34",
        "$PSTI,030,033010.000,A,2447.0895508,N,12100.5234656,E,94.615,0.00,-0.01,0.04,111219,R,0.999,3.724*1A",
        "$PSTI,032,033010.000,111219,A,R,-4.968,-10.817,-1.849,12.046,204.67,,,,,*39",
        "$PSTI,033,110431.000,150517,2,R,1,G,1,0,,,C,0,0,,,E,0,0,,,R,0,0,,*72",
        "$PSTI,035,041457.000,170316,A,R,0.603,-0.837,-0.089,1.036,144.22,,,,,*1B",
    ]

    p = NMEAParser(track_satellites=True)
    for line in sample_lines:
        ok = p.feed_line(line)
        print(f"{ok}  {line}")

    print(p.get_state())
