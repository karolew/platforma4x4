● Najprościej: zrób tunel SSH z portu 1883 na Pi do lokalnego 1883, i uruchom heading_demo.py na swoim PC wskazując na 127.0.0.1.

  1. Tunel SSH (zostaw otwarty na czas dema):
  ssh -L 1883:localhost:1883 <user>@<adres-raspberry-pi>
  (działa w PowerShell z wbudowanym OpenSSH na Windows 11 — nic dodatkowego nie trzeba instalować)

  To przekierowuje: localhost:1883 na Twoim PC → localhost:1883 na Pi (czyli dokładnie tam, gdzie mosquitto nasłuchuje).

  2. W drugim oknie terminala na PC, uruchom demo:
  python heading_demo\heading_demo.py --host 127.0.0.1 --port 1883 --rover-id rover-01
  (--rover-id dopasuj, jeśli w rover/config/rover.yaml na Pi jest inny niż rover-01)

  Tunel musi być aktywny przez cały czas działania GUI — jak zamkniesz SSH, demo przestanie dostawać dane (pokaże "rozłączony" / "BRAK HEADING").

  Jeśli wolisz, żeby tunel trzymał się w tle bez zajmowania terminala, dodaj -N -f (Linux/macOS) — na Windows OpenSSH -N działa, ale -f (fork w tło) nie jest wspierane; zamiast tego po prostu zminimalizuj to okno albo
  uruchom przez Start-Process ssh -ArgumentList "-N","-L","1883:localhost:1883","<user>@<pi>".
