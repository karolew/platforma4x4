"""Szybkie przypiecie sieci i stalego IP na biezacej sieci, przez nmcli.

Uzycie (na anana, wymaga uprawnien do nmcli - zwykle sudo):
    sudo python3 rover/scripts/set_static_ip.py eth
    sudo python3 rover/scripts/set_static_ip.py wifi <ssid> [haslo]
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys

STATIC_LAST_OCTET = 102
LOG_PATH = f"/tmp/set_static_ip.{os.geteuid()}.log"


def survive_disconnect() -> None:
    """Ten skrypt sam przelacza siec, wiec sesja SSH przez ktora go uruchomiono
    zrywa sie w trakcie dzialania - bez tego proces ginalby razem z nia (SIGHUP)
    zanim zdazy dokonczyc ustawianie static IP."""
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        os.setsid()
    except OSError:
        pass  # juz lider sesji/grupy - nic do zrobienia, ale SIGHUP i tak ignorowany


def log(msg: str, err: bool = False) -> None:
    try:
        with open(LOG_PATH, "a") as f:
            f.write(msg + "\n")
    except OSError:
        pass  # brak dostepu do pliku logu (np. inny wlasciciel po sudo) - nie przerywaj skryptu
    try:
        print(msg, file=sys.stderr if err else sys.stdout, flush=True)
    except OSError:
        pass  # terminal juz nie istnieje (SSH sie rozlaczyl) - log na dysku wystarczy


def run(*args: str) -> str:
    result = subprocess.run(["nmcli", *args], capture_output=True, text=True)
    if result.returncode != 0:
        log(result.stderr.strip(), err=True)
        sys.exit(1)
    return result.stdout.strip()


def print_all_devices() -> None:
    for line in run("device", "status").splitlines():
        log(line)
    for line in run("device", "wifi", "list").splitlines():
        log(line)


def find_active_connection(device: str) -> str:
    for line in run("-t", "-f", "NAME,DEVICE", "con", "show", "--active").splitlines():
        name, dev = line.rsplit(":", 1)
        if dev == device:
            return name
    log(f"Brak aktywnego polaczenia na {device} - polacz sie najpierw normalnie (DHCP).", err=True)
    sys.exit(1)


def active_wifi_ssid() -> str | None:
    for line in run("-t", "-f", "active,ssid", "dev", "wifi").splitlines():
        active, ssid = line.split(":", 1)
        if active == "yes":
            return ssid
    return None


def current_ip_info(device: str) -> tuple[str, str, str]:
    address_cidr = run("-g", "IP4.ADDRESS", "device", "show", device).splitlines()[0]
    ip, prefix = address_cidr.split("/")
    gateway = run("-g", "IP4.GATEWAY", "device", "show", device).splitlines()[0]
    return ip, prefix, gateway


def make_static_ip(ip: str) -> str:
    octets = ip.split(".")
    octets[-1] = str(STATIC_LAST_OCTET)
    return ".".join(octets)


def connection_exists(name: str) -> bool:
    return name in run("-t", "-f", "NAME", "con", "show").splitlines()


def connect_wifi(ssid: str, password: str | None) -> None:
    if connection_exists(ssid):
        # stary/niekompletny profil (np. brak wifi-sec.key-mgmt) powoduje
        # "property is missing" przy probie ponownego polaczenia - usuwamy
        # go, zeby nmcli zbudowal nowy, kompletny profil od zera.
        run("con", "delete", ssid)
    args = ["device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    run(*args)
    log(f"Polaczono z siecia '{ssid}'.")


def main() -> None:
    survive_disconnect()
    args = sys.argv[1:]

    if not args or args[0] not in ("eth", "wifi"):
        log("Uzycie: set_static_ip.py eth | wifi <ssid> [haslo]")
        print_all_devices()
        sys.exit(1)

    device = "eth0" if args[0] == "eth" else "wlan0"

    if args[0] == "wifi":
        if len(args) < 2:
            log("Uzycie: set_static_ip.py wifi <ssid> [haslo]")
            sys.exit(1)
        ssid = args[1]
        password = args[2] if len(args) > 2 else None
        if active_wifi_ssid() != ssid:
            connect_wifi(ssid, password)

    connection = find_active_connection(device)
    ip, prefix, gateway = current_ip_info(device)
    static_ip = make_static_ip(ip)

    log(f"[{device}] polaczenie '{connection}', DHCP: {ip}/{prefix}, gateway: {gateway}")
    log(f"[{device}] przelaczam na staly IP: {static_ip}/{prefix}")
    log("Jesli laczysz sie przez SSH polaczenie za chwile sie zerwie - skrypt dokonczy dzialanie w tle, patrz " + LOG_PATH)

    run(
        "con", "mod", connection,
        "ipv4.method", "manual",
        "ipv4.addresses", f"{static_ip}/{prefix}",
        "ipv4.gateway", gateway,
        "ipv4.dns", f"{gateway} 8.8.8.8",
    )
    run("con", "up", connection)

    log(static_ip)


if __name__ == "__main__":
    main()
