#!/bin/bash
set -euo pipefail

SRC=/tmp/rover-deploy

# Wyczyść dane git.
rm -rf "$SRC/.git"

# Zmień ID rovera jeśli parametr podany.
if [ -n "${1:-}" ]; then
    echo "Zmiana ROVER ID na $1"
    sudo -u rover sed -i "s/^rover_id: .*/rover_id: $1/" /opt/rover/config/rover.yaml
fi

# Synchronizuj wyłącznie kod źródłowy - config/pyproject/deploy z payloadu ignorowane,
# żeby nie nadpisać lokalnych zmian configu zrobionych bezpośrednio na RPi.
sudo rsync -av --delete "$SRC/src/" /opt/rover/src/
sudo chown -R rover:rover /opt/rover/src
rm -rf "$SRC"

sudo systemctl restart rover-motion rover-navigation rover-vision rover-sensors rover-actuators rover-decision rover-planner-link
sleep 5
systemctl status rover-motion rover-navigation rover-vision rover-sensors rover-actuators rover-decision rover-planner-link --no-pager
