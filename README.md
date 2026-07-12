# ROVER — deploy na Raspberry Pi

Zakładany sprzęt: Raspberry Pi 3, Raspberry Pi OS Lite (64-bit), moduł CAN podłączony po SPI (np. HAT na MCP2515 — dopasuj `dtoverlay` do swojego HAT-a).

## 1. Karta SD

1. Wypal **Raspberry Pi OS Lite (64-bit)** przez Raspberry Pi Imager.
2. W ustawieniach Imagera (ikona koła zębatego) ustaw od razu: hostname (np. `rover-01`), włącz SSH, użytkownika/hasło, Wi-Fi (jeśli potrzebne).
3. Wsadź kartę, uruchom RPi, połącz się:
   ```bash
   ssh <user>@rover-01.local
   ```

## 2. Aktualizacja systemu

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

## 3. Interfejs CAN

1. Włącz SPI:
   ```bash
   sudo raspi-config nonint do_spi 0
   ```
2. Dodaj overlay CAN w `/boot/firmware/config.txt` (na starszych obrazach: `/boot/config.txt`):
   ```
   dtparam=spi=on
   dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25,spimaxfrequency=1000000
   ```
   Wartości zweryfikowane na module **HW-184** (MCP2515 + transceiver VP230, zasilanie 3.3V, kryształ 8 MHz) — sprawdź kryształ na swojej płytce, jeśli masz inny moduł (`dmesg | grep -i mcp2515` po reboocie musi pokazać `successfully initialized`). `interrupt` to numer GPIO podłączony do pinu INT modułu (tu: GPIO25) — dopasuj jeśli okablowałeś inaczej. **CS musi być podłączony** (GPIO8/CE0) — bez niego MCP2515 się nie zainicjalizuje.
3. Zainstaluj narzędzia CAN i podnieś interfejs:
   ```bash
   sudo apt install -y can-utils
   sudo ip link set can0 up type can bitrate 500000
   ```
4. Test (na innym urządzeniu w magistrali lub pętli zwrotnej):
   ```bash
   candump can0
   ```
5. Podniesienie `can0` na starcie — utwórz `/etc/systemd/network/80-can.network`:
   ```ini
   [Match]
   Name=can0

   [CAN]
   BitRate=500000

   [Link]
   RequiredForOnline=no
   ```
   ```bash
   sudo systemctl enable systemd-networkd
   ```

## 4. Python 3.13

Sprawdź najpierw czy już masz 3.13+ (część obrazów/aktualizacji Raspberry Pi OS już go ma):

```bash
python3.13 --version
```

Jeśli brak — Raspberry Pi OS Lite (Debian 12 „Bookworm") ma domyślnie Python 3.11, trzeba doinstalować 3.13. Najprościej przez `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv python install 3.13
```

## 5. Mosquitto (broker MQTT)

```bash
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl stop mosquitto   # wystartuje docelowo jako część configu poniżej
```

## 6. Użytkownik i katalog aplikacji

```bash
sudo useradd -r -m -d /opt/rover -s /usr/sbin/nologin rover
sudo usermod -aG dialout,spi rover   # dostęp do CAN/serial
```

## 7. Wgranie kodu

Z maszyny deweloperskiej (zamień `rover-01.local` na hostname/IP Twojego RPi):

```bash
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='.git' --exclude='.gitignore' \
  ./rover/ <user>@rover-01.local:/tmp/rover-deploy/
```

Windows / Git Bash (bez `rsync`):

```bash
scp -r rover <user>@rover-01.local:/tmp/rover-deploy
```

**Uwaga**: `scp -r` kopiuje poprawnie (płasko) tylko gdy `/tmp/rover-deploy` **jeszcze nie istnieje** na RPi. Jeśli katalog już istnieje z poprzedniej próby, `scp` zagnieżdża źródło w środku zamiast nadpisać zawartość (namieszane ścieżki typu `/opt/rover/src/src/...` po kolejnym kroku). Przy pierwszym deployu katalog na pewno nie istnieje, więc tutaj bezpiecznie — ale przy kolejnych aktualizacjach kodu używaj `deploy/sync-rover.sh` (sekcja „Aktualizacja kodu” niżej), który sam się o to czyszczenie troszczy.

Na RPi:

```bash
sudo rsync -av /tmp/rover-deploy/ /opt/rover/
sudo chown -R rover:rover /opt/rover
rm -rf /tmp/rover-deploy
```

## 8. Instalacja zależności

Przełącz się na użytkownika `rover` (nie `sudo` — pliki mają należeć do `rover`, nie do `root`, bo tak uruchamiają się serwisy w kroku 11):

```bash
sudo -u rover -H bash
cd /opt/rover
python3.13 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[motion,sensors,navigation,actuators,planner]"
```

Extra `vision` (OpenCV) dołącz tylko jeśli ten RPi faktycznie obsługuje kamerę — instalacja jest zauważalnie cięższa na RPi3:

```bash
pip install -e ".[vision]"
```

(Jeśli zamiast systemowego `python3.13` zainstalowałeś go przez `uv` w kroku 4, użyj `uv venv --python 3.13 .venv` i `uv pip install -e "..."` zamiast powyższego — działa tak samo, tylko szybciej.)

## 9. Konfiguracja

Edytuj `/opt/rover/config/rover.yaml` (unikalny `rover_id` per robot) oraz pliki w `/opt/rover/config/services/*.yaml` — zmień `driver: mock` na docelowy driver (`stm32_can`, `rtk_gnss`, `opencv_path`, `can_collision`, `servo_can`, `rest_ws`) w miarę jak poszczególne implementacje są gotowe. Dopóki dana implementacja ma `raise NotImplementedError`, zostaw tam `mock`.

## 10. Broker MQTT — config

```bash
sudo cp /opt/rover/deploy/mosquitto/mosquitto.conf /etc/mosquitto/conf.d/rover.conf
sudo systemctl enable --now mosquitto
```

## 11. Systemd — serwisy ROVER

```bash
sudo cp /opt/rover/deploy/systemd/rover-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rover-motion rover-navigation rover-vision \
  rover-sensors rover-actuators rover-decision rover-planner-link
```

Uwaga: unity w repo wskazują na `/opt/rover/.venv/bin/python` — jeśli zmieniasz ścieżkę instalacji, popraw `ExecStart` w plikach `.service` przed kopiowaniem.

## 12. Weryfikacja

```bash
systemctl status rover-decision
journalctl -u rover-motion -f
mosquitto_sub -h localhost -t 'rover/+/#' -v
```

Powyższe powinno pokazywać przepływające wiadomości na topikach `rover/<rover_id>/...` (na driverach `mock` zobaczysz np. `decision/drive_cmd` i `motion/status`).

## Aktualizacja kodu (redeploy)

Do szybkich iteracji nad kodem (bez zmian w zależnościach/pyproject) służy `deploy/sync-rover.sh` — kopiuje tylko `src/`, zostawia `config/` na RPi nietknięty (chyba że podasz nowy `rover_id`), i restartuje wszystkie serwisy. Jest już na RPi po kroku 7 (część `deploy/`), trzeba go tylko raz uczynić wykonywalnym:

```bash
chmod +x /opt/rover/deploy/sync-rover.sh
```

Sam cykl aktualizacji, za każdym razem:

```bash
# z maszyny dev (Linux/macOS)
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='.git' --exclude='.gitignore' \
  ./rover/ <user>@rover-01.local:/tmp/rover-deploy/
# z maszyny dev (Windows / Git Bash)
scp -r rover <user>@rover-01.local:/tmp/rover-deploy
```

Na RPi:

```bash
bash /opt/rover/deploy/sync-rover.sh            # bez zmiany rover_id
bash /opt/rover/deploy/sync-rover.sh robal-002   # ze zmianą rover_id
```

Skrypt sam usuwa `/tmp/rover-deploy` na końcu, więc kolejny `scp -r` zawsze trafia na nieistniejący katalog docelowy (bezpieczne pod kątem opisanej wyżej pułapki `scp -r`). Jeśli zmieniły się zależności (`pyproject.toml`) albo systemd unity (`deploy/systemd/*.service`) — to trzeba zaktualizować ręcznie, `sync-rover.sh` tego celowo nie robi (patrz kroki 8 i 11).

## Troubleshooting

- **`can0` nie istnieje** → sprawdź `dmesg | grep -i mcp2515`, złe okablowanie SPI lub zły `oscillator` w overlay.
- **Serwis restartuje w pętli** → `journalctl -u rover-<nazwa> -n 50 --no-pager`, zwykle brak uprawnień do `/dev/spidev*` lub `can0` (grupa `rover` bez `dialout`/`spi`), albo błąd w `config/services/*.yaml`.
- **Serwisy nie widzą się nawzajem** → sprawdź czy `mosquitto` działa (`systemctl status mosquitto`) i czy `mqtt.host`/`port` w `config/rover.yaml` są poprawne.
- **Serwis mock crash-looping z `TypeError: Mock...() takes no arguments`** → `driver_args` z configu (przeznaczone dla drivera docelowego) trafiają też do drivera `mock`; wszystkie klasy `Mock*` mają `def __init__(self, **_kwargs) -> None: ...` właśnie po to, żeby to ignorować — jeśli błąd wraca, sprawdź czy deploy faktycznie nadpisał plik (patrz punkt niżej o `scp -r`).
- **Kod na RPi nie zgadza się z lokalnym mimo "udanego" transferu** → jeśli `scp -r local user@host:remote_dir` trafił na już istniejący `remote_dir` (np. przerwany poprzedni sync), `scp` zagnieżdża `local` W ŚRODKU `remote_dir` zamiast nadpisać jego zawartość (namieszane katalogi typu `/opt/rover/src/src/...`). Sprawdź `find /opt/rover/src -maxdepth 2` czy nie ma duplikatów; przed kolejnym `scp -r ...:/tmp/rover-deploy` zrób ręcznie `ssh <user>@rover-01.local 'rm -rf /tmp/rover-deploy'`. Używanie `deploy/sync-rover.sh` do aktualizacji (patrz sekcja „Aktualizacja kodu") zapobiega temu na stałe, bo sam sprząta po sobie na końcu każdego uruchomienia.
