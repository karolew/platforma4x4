"""Parser NMEA - docelowo oparty o github.com/karolew/microNMEA (pojedynczy plik,
pisany pod MicroPython), zvendorowany/dostosowany do tego projektu.

parse() ma aktualizowac atrybuty ponizej na podstawie kolejnych zdan NMEA
(GGA/RMC/VTG oraz PSTI,032 / PSTI,035 dla heading/baseline w trybie moving base).
"""
from __future__ import annotations


class NMEAParser:

    QUALITY = (
        "Fix Unavailable",
        "SPS Fix",
        "DGPS Fix",
        "PPS Fix",
        "RTK Fix",
        "RTK Float",
        "Estimated (dead reckoning) Mode",
        "Manual Input Mode",
        "Simulator Mode"
    )

    MODES = {
        "A": "Autonomous Mode",
        "D": "Differential Mode",
        "E": "Estimated (dead reckoning) Mode",
        "M": "Manual Mode",
        "S": "Simulator Mode",
        "N": "Data Not Valid",
        "V": "Data Not Valid",
        "R": "RTK Fix",
        "F": "RTK Float",
        "P": "Precise"
    }

    NAV_STATUS = {
        "S": "Safe",
        "C": "Caution",
        "U": "Unsafe",
        "V": "Not Valid"
    }

    GNSS_IDS = {
        1: {"system": "GPS", "talker": "GP", "signals": {
                                                         "0": "All signals",
                                                         "1": "L1 C/A",
                                                         "2": "L1 P(Y)",
                                                         "3": "L1C",
                                                         "4": "L2 P(Y)",
                                                         "5": "L2C-M",
                                                         "6": "L2C-L",
                                                         "7": "L5-I",
                                                         "8": "L5-Q"}},
        2: {"system": "GLONASS", "talker": "GL", "signals": {
                                                         "0": "All signals",
                                                         "1": "G1 C/A",
                                                         "2": "G1P",
                                                         "3": "G2 C/A",
                                                         "4": "GLONASS (M) G2P"}},
        3: {"system": "GALILEO", "talker": "GA", "signals": {
                                                         "0": "All signals",
                                                         "1": "E5a",
                                                         "2": "E5b",
                                                         "3": "E5 a+b",
                                                         "4": "E6-A",
                                                         "5": "E6-BC",
                                                         "6": "L1-A",
                                                         "7": "L1-BC"}},
        4: {"system": "BDS", "talker": "GB", "signals": {
                                                         "0": "All signals",
                                                         "1": "B1",
                                                         "5": "B2A",
                                                         "B": "B2",
                                                         "8": "B3",
                                                         "3": "B1C"}},
        5: {"system": "IRNSS", "talker": "GI", "signals": {
                                                         "0": "All signals",
                                                         "4": "L2 P(Y) "}}
    }

    HEMISPHERES = (
        "N", "S", "E", "W"
    )

    SEN_START = "$"
    SEN_SEPARATOR = ","
    SEN_CRC = "*"
    VALID = "A"
    SPEED_KNOTS_2_KMH = 1.852

    def __init__(self, units: int = 1, formats: int = 2, crc: bool = True) -> None:
        self.units = units
        self.formats = formats
        self.crc = crc
        self.fields = []
        self.time = None
        self.lat = None
        self.lat_ns = None
        self.lon = None
        self.lon_ew = None
        self.alt = None     # alt_m
        self.quality = None     # fix_type
        self.mode = None
        self.number_of_satellites_used = None   # num_satellites
        self.satellites_used = dict()
        self.hdop = None
        self.vdop = None
        self.pdop = None
        self.dgps_station_id = None
        self.dgps_age = None
        self.geoidal_separation = None
        self.__tmp_gsv_part = dict()
        self.gsv_data = dict()
        self.speed = None       # speed_kmh
        self.course = None
        self.date = None
        self.heading = None     # heading_deg
        self.heading_mode = None
        self.east_velocity = None
        self.north_velocity = None
        self.up_velocity = None
        self.rtk_age = None
        self.rtk_ratio = None
        self.east_pob = None
        self.north_pob = None
        self.up_pob = None
        self.baseline_length = None     # baseline_m, z PSTI,035 (Base<->Rover, jedyny fizyczny link w tym projekcie)
        self.baseline_course = None     # z PSTI,035 - patrz baseline_length
        self.baseline_mode = None       # RTK ambiguity mode PSTI,035: F=Float, R=Fix - patrz baseline_length
        self.nav_status = None

        # PSTI,032 (link CORS<->Base w Advanced Moving Base) - w tym projekcie nieuzywany (brak fizycznego
        # Receiver A, NTRIP wpiety bezposrednio w Base), dane bez sensu fizycznego (baseline_length rosnie
        # bez ograniczen). Trzymane w OSOBNYCH atrybutach, zeby nie nadpisywaly prawdziwych danych z PSTI,035.
        self.east_pob_032 = None
        self.north_pob_032 = None
        self.up_pob_032 = None
        self.baseline_length_032 = None
        self.baseline_course_032 = None
        self.mode_032 = None

    def parse(self, raw_sentence: str) -> None:
        try:
            if raw_sentence == "" or raw_sentence[0] != self.SEN_START or self.SEN_CRC not in raw_sentence:
                print("Sentence empty or incomplete.")
                return
            # STI messages key differs from other sentences. They have shorter sentence prefix and additional ID field.
            sentence_type = raw_sentence[2:5] if "STI" in raw_sentence else raw_sentence[3:6]
            sentence, expected_crc = raw_sentence.split(self.SEN_CRC)
            if self.crc_check(sentence, expected_crc):
                __call = getattr(self, sentence_type.lower(), None)
                self.fields = sentence.split(self.SEN_SEPARATOR)
                if __call:
                    try:
                        __call()
                    except Exception as e:
                        print(f"ERROR of {sentence_type} sentence. {e}")
                else:
                    print(f"Not supported sentence: {sentence_type}")
            else:
                print(f"Incorrect CRC for {sentence_type}")
        except Exception as e:
            print(f"ERROR of parse. {e}")

    def crc_check(self, message: str, expected_crc: str) -> bool:
        # Skip CRC check.
        if not self.crc:
            return True

        crc = 0
        for __char in message[1:]:
            crc ^= ord(__char)
        return f"0x{crc:02x}".lower()[2:] == expected_crc.lower()

    def get_lat(self, lat: str, lns: str) -> None:
        if lat and lns and lns in self.HEMISPHERES:
            # Raw
            if self.formats == 1:
                self.lat = lat
                self.lat_ns = lns
            # dd
            elif self.formats == 2:
                la_deg = lat[:2]
                la_minutes = lat[2:]
                decimal_degrees = float(la_deg) + float(la_minutes) / 60
                self.lat = (-1 if lns.lower() == 's' else 1) * decimal_degrees
                self.lat_ns = lns

    def get_lon(self, lon: str, lew: str) -> None:
        if lon and lew and lew in self.HEMISPHERES:
            # Raw
            if self.formats == 1:
                self.lon = lon
                self.lon_ew = lew
            # dd
            elif self.formats == 2:
                lo_deg = lon[:3]
                lo_minutes = lon[3:]
                decimal_degrees = float(lo_deg) + float(lo_minutes) / 60
                self.lon = (-1 if lew.lower() == 's' else 1) * decimal_degrees
                self.lon_ew = lew

    def get_quality(self, field: str) -> None:
        if field and int(field) in range(len(self.QUALITY)):
            self.quality = self.QUALITY[int(field)]

    def get_satellites_used(self, field: str) -> None:
        if field:
            self.number_of_satellites_used = int(field)

    def get_satellites_used_list(self, gnss_id: str, satellites: list) -> None:
        if gnss_id and int(gnss_id) in self.GNSS_IDS and satellites:
            self.satellites_used[self.GNSS_IDS[int(gnss_id)]["system"]] = satellites

    def get_pdop(self, field: str) -> None:
        if field and 0 < float(field) < 100:
            self.pdop = float(field)

    def get_hdop(self, field: str) -> None:
        if field and 0 < float(field) < 100:
            self.hdop = float(field)

    def get_vdop(self, field: str) -> None:
        if field and 0 < float(field) < 100:
            self.vdop = float(field)

    def get_alt(self, field: str) -> None:
        if field:
            self.alt = float(field)

    def get_dgps_station_id(self, field: str) -> None:
        if field:
            self.dgps_station_id = int(field)

    def get_dgps_age(self, field: str) -> None:
        if field:
            self.dgps_age = field

    def get_geoidal_separation(self, field: str) -> None:
        if field:
            self.geoidal_separation = float(field)

    def get_time(self, field: str) -> None:
        if field:
            if self.units == 1:
                self.time = field
            elif self.units == 2:
                self.time = f"{field[:2]}:{field[2:4]}:{field[4:]}"

    def get_date(self, field: str) -> None:
        if field:
            if self.units == 1:
                self.date = field
            elif self.units == 2:
                dd = field[:2]
                mm = field[2:4]
                yy = field[4:]
                self.date = f"{2000 + int(yy)}-{mm}-{dd}"

    def get_date_2(self, day: str, month: str, year: str) -> None:
        if day and month and year:
            if self.units == 1:
                self.date = f"{day}{month}{year[2:]}"
            elif self.units == 2:
                self.date = f"{year}-{month}-{day}"

    def get_mode(self, field: str) -> None:
        if field and field in self.MODES:
            self.mode = self.MODES.get(field)

    def get_heading_mode(self, field: str) -> None:
        if field and field in self.MODES:
            self.heading_mode = self.MODES.get(field)

    def get_speed(self, field: str) -> None:
        if field:
            speed_knots = float(field)
            if self.units == 1:
                self.speed = speed_knots
            elif self.units == 2:
                self.speed = round(speed_knots * self.SPEED_KNOTS_2_KMH, 2)

    def get_course(self, field: str) -> None:
        if field:
            self.course = float(field)

    def get_heading(self, field: str) -> None:
        if field:
            self.heading = float(field)

    def get_east_velocity(self, field: str) -> None:
        if field:
            self.east_velocity = float(field)

    def get_north_velocity(self, field: str) -> None:
        if field:
            self.north_velocity = float(field)

    def get_up_velocity(self, field: str) -> None:
        if field:
            self.up_velocity = float(field)

    def get_rtk_age(self, field: str) -> None:
        if field:
            self.rtk_age = float(field)

    def get_rtk_ratio(self, field: str) -> None:
        if field:
            self.rtk_ratio = float(field)

    def get_east_pob(self, field) -> None:
        if field:
            self.east_pob = float(field)

    def get_north_pob(self, field) -> None:
        if field:
            self.north_pob = float(field)

    def get_up_pob(self, field) -> None:
        if field:
            self.up_pob = float(field)

    def get_baseline_length(self, field) -> None:
        if field:
            self.baseline_length = float(field)

    def get_baseline_course(self, field) -> None:
        if field:
            self.baseline_course = float(field)

    def get_nav_status(self, field) -> None:
        if field and field in self.NAV_STATUS:
            self.nav_status = self.NAV_STATUS.get(field)

    def gga(self) -> None:
        """
         Global positioning system fix data.
        """
        self.get_quality(self.fields[6])
        if self.quality != self.QUALITY[0]:
            self.get_time(self.fields[1])
            self.get_lat(self.fields[2], self.fields[3])
            self.get_lon(self.fields[4], self.fields[5])
            self.get_satellites_used(self.fields[7])
            self.get_hdop(self.fields[8])
            self.get_alt(self.fields[9])
            self.get_geoidal_separation(self.fields[11])
            self.get_dgps_age(self.fields[13])
            self.get_dgps_station_id(self.fields[14])

    def gll(self) -> None:
        """
         Geographic position latitude and longitude.
        """
        self.get_mode(self.fields[7])
        if (self.fields[6] == self.VALID
                and self.fields[7] != self.MODES["N"]):
            self.get_lat(self.fields[1], self.fields[2])
            self.get_lon(self.fields[3], self.fields[4])
            self.get_time(self.fields[5])

    def gsa(self) -> None:
        """
         GNSS DOP and active satellites.
        """
        self.get_satellites_used_list(self.fields[18], self.fields[3:15])
        self.get_pdop(self.fields[15])
        self.get_hdop(self.fields[16])
        self.get_vdop(self.fields[17])

    def gsv(self) -> None:
        """
        GNSS satellites in view.

        GSV sentence may be part of bigger message. This means all sentences of the
        message must be read to get correct content. Correct satellites data are in
        gsv_data attribute.
        """
        # Check GNSS is supported.
        talker = self.fields[0][1:3]

        if not any(talker in x["talker"] for x in self.GNSS_IDS.values()):
            # Talker incorrect or not supported.
            return

        if self.fields[1] and self.fields[2]:
            number_of_messages = int(self.fields[1])
            sentence_number = int(self.fields[2])
            if self.fields[3]:
                if talker not in self.__tmp_gsv_part:
                    self.__tmp_gsv_part[talker] = {"satellites_in_view": 0, "satellites": dict()}
                self.__tmp_gsv_part[talker]["satellites_in_view"] = int(self.fields[3])
                if len(self.fields) <= 5:
                    # Nothing else to update.
                    return
                else:
                    for offset in range(4, len(self.fields[4:]), 4):
                        satellite_id, elev, azim, snr = self.fields[offset:offset+4]
                        if satellite_id:
                            __sats = {int(satellite_id): [int(elev) if elev else "NA",
                                                          int(azim) if azim else "NA",
                                                          int(snr) if snr else "NA"]}
                            self.__tmp_gsv_part[talker]["satellites"].update(__sats)
            if (sentence_number == number_of_messages and
                    len(self.__tmp_gsv_part[talker]["satellites"]) ==
                    self.__tmp_gsv_part[talker]["satellites_in_view"]):
                self.gsv_data = self.__tmp_gsv_part

    def rmc(self) -> None:
        """
        Recommended minimum specific GNSS data
        """
        self.get_mode(self.fields[12])
        self.get_nav_status(self.fields[13])
        if (self.fields[2] == self.VALID
                and self.nav_status  not in [self.NAV_STATUS["V"], self.NAV_STATUS["U"]]
                and self.mode != self.MODES["N"]):
            self.get_time(self.fields[1])
            self.get_lat(self.fields[3], self.fields[4])
            self.get_lon(self.fields[5], self.fields[6])
            self.get_speed(self.fields[7])
            self.get_course(self.fields[8])
            self.get_date(self.fields[9])

    def vtg(self) -> None:
        """
        Course Over Ground and Ground Speed.
        """
        self.get_mode(self.fields[9])
        if self.fields[9] != "N":
            # fields[1]=course (True), fields[5]=speed w wezlach - wg datasheetu PX1122R str.21
            self.get_course(self.fields[1])
            self.get_speed(self.fields[5])

    def zda(self) -> None:
        """
        Time and date.
        """
        self.get_time(self.fields[1])
        self.get_date_2(self.fields[2], self.fields[3], self.fields[4])

    def ths(self) -> None:
        """
        True Heading and Status.
        """
        self.get_heading_mode(self.fields[2])
        if self.fields[2] != "V":
            self.get_heading(self.fields[1])

    def sti(self) -> None:
        """
        STI 005 Time Stamp Output
        STI 030 Recommended Minimum 3D GNSS Data
        STI 032 RTK Baseline Data - link CORS(A)<->Base(B) w Advanced Moving Base; NIEUZYWANY w tym
        projekcie (2 odbiorniki, NTRIP wpiety bezposrednio w Base zamiast fizycznego Receiver A) - dane
        bez sensu fizycznego, potwierdzone na sprzecie (baseline_length rosnie bez ograniczen, >137m).
        Trzymane w oddzielnych *_032 atrybutach, celowo NIE dzieli pol z PSTI,035 ponizej.
        TODO STI 033 RTK RAW Measurement Monitoring Data
        STI 035 RTK Baseline Data of Rover Moving Base Receiver - link Base(B)<->Rover(C), jedyny
        fizycznie istniejacy w tym projekcie - zrodlo baseline_length/baseline_course/heading_deg.
        """
        if "005" in self.fields[1]:
            self.get_time(self.fields[2])
            self.get_date_2(self.fields[3], self.fields[4], self.fields[5])

        elif "030" in self.fields[1]:
            if self.fields[3] == self.VALID:
                self.get_time(self.fields[2])
                self.get_lat(self.fields[4], self.fields[5])
                self.get_lon(self.fields[6], self.fields[7])
                self.get_alt(self.fields[8])
                self.get_east_velocity(self.fields[9])
                self.get_north_velocity(self.fields[10])
                self.get_up_velocity(self.fields[11])
                self.get_date(self.fields[12])
                self.get_mode(self.fields[13])
                self.get_rtk_age(self.fields[14])
                self.get_rtk_ratio(self.fields[15])

        elif "032" in self.fields[1]:
            if self.fields[4] == self.VALID:
                if self.fields[5] and self.fields[5] in self.MODES:
                    self.mode_032 = self.MODES[self.fields[5]]
                self.east_pob_032 = float(self.fields[6]) if self.fields[6] else None
                self.north_pob_032 = float(self.fields[7]) if self.fields[7] else None
                self.up_pob_032 = float(self.fields[8]) if self.fields[8] else None
                self.baseline_length_032 = float(self.fields[9]) if self.fields[9] else None
                self.baseline_course_032 = float(self.fields[10]) if self.fields[10] else None

        elif "035" in self.fields[1]:
            if self.fields[4] == self.VALID:
                self.get_time(self.fields[2])
                self.get_date(self.fields[3])
                if self.fields[5] and self.fields[5] in self.MODES:
                    self.baseline_mode = self.MODES[self.fields[5]]
                self.get_east_pob(self.fields[6])
                self.get_north_pob(self.fields[7])
                self.get_up_pob(self.fields[8])
                self.get_baseline_length(self.fields[9])
                self.get_baseline_course(self.fields[10])
            else:
                # baseline_course NIE jest czyszczony - zostaje przy ostatniej znanej
                # wartosci (stale), wiec bez tego printu zamrozenie heading jest ciche.
                print("PSTI,035: baseline invalid (V) - heading_deg zamrozony na ostatniej wartosci")

        elif "033" in self.fields[1]:
            print("STI 033 not implemented")

        else:
            print(f"Unknown STI ID: {self.fields[1]}")

    def __repr__(self) -> str:
        return (f"Time: {self.time}\n"
                f"Date: {self.date}\n"
                f"Latitude: {self.lat} {self.lat_ns}\n"
                f"Longitude: {self.lon} {self.lon_ew}\n"
                f"Altitude {self.alt}\n"
                f"Quality Indicator: {self.quality}\n"
                f"Mode Indicator: {self.mode}\n"
                f"Number of satellites used: {self.number_of_satellites_used}\n"
                f"Statellites used: {self.satellites_used}\n"
                f"Geoidal Separation: {self.geoidal_separation}\n"
                f"Age of DGPS data: {self.dgps_age}\n"
                f"DGPS station ID: {self.dgps_station_id}\n"
                f"PDOP: {self.pdop}\n"
                f"HDOP: {self.hdop}\n"
                f"VDOP: {self.vdop}\n"
                f"GNSS satellites in view: {self.gsv_data}\n"
                f"Speed: {self.speed}\n"
                f"Course: {self.course}\n"
                f"Heading: {self.heading}\n"
                f"East velocity: {self.east_velocity}\n"
                f"North velocity: {self.north_velocity}\n"
                f"Up velocity: {self.up_velocity}\n"
                f"RTK age: {self.rtk_age}\n"
                f"RTK ratio: {self.rtk_ratio}\n"
                f"East-projection of baseline: {self.east_pob}\n"
                f"North-projection of baseline: {self.north_pob}\n"
                f"Up-projection of baseline: {self.up_pob}\n"
                f"Baseline length: {self.baseline_length}\n"
                f"Baseline course: {self.baseline_course}\n"
                f"Navigation status: {self.nav_status}"
                )
