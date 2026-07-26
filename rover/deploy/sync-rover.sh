#!/bin/bash
set -euo pipefail

SRC=~/rover

# Wyczyść dane git.
rm -rf "$SRC/.git"

# Zmień ID rovera jeśli parametr podany.
if [ -n "${1:-}" ]; then
    echo "Zmiana ROVER ID na $1"
    sudo -u rover sed -i "s/^rover_id: .*/rover_id: $1/" /opt/rover/config/rover.yaml
fi

# Wykryj zmianę pyproject.toml przed synchronizacją (wymaga ręcznego pip install w venv).
PYPROJECT_CHANGED=0
if ! cmp -s "$SRC/pyproject.toml" /opt/rover/pyproject.toml 2>/dev/null; then
    PYPROJECT_CHANGED=1
fi

# Synchronizuj całość poza config/ (per-rover dane - NTRIP creds, rover_id - istnieją tylko na RPi,
# repo trzyma puste placeholdery) i .venv/ (nigdy nie ma go w payloadzie - --delete by je skasował).
sudo rsync -av --delete --exclude='config/' --exclude='.venv/' "$SRC/" /opt/rover/
sudo chown -R rover:rover /opt/rover
rm -rf "$SRC"

if [ "$PYPROJECT_CHANGED" -eq 1 ]; then
    echo "UWAGA: pyproject.toml się zmienił - doinstaluj zależności ręcznie:"
    echo "  sudo -u rover -H bash -c 'cd /opt/rover && source .venv/bin/activate && pip install -e \".[motion,sensors,navigation,actuators,planner]\"'"
fi

sudo systemctl restart rover-motion rover-navigation rover-vision rover-sensors rover-actuators rover-decision rover-planner-link
sleep 5
systemctl status rover-motion rover-navigation rover-vision rover-sensors rover-actuators rover-decision rover-planner-link --no-pager

