#!/usr/bin/env bash
# Appium serverini ise salir (sudo TELEB OLUNMUR).
# Bu pencereni aciq saxla.
set -e

export PATH="$HOME/.local/node-current/bin:$PATH"
export DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer"

echo "Node:   $(node --version)"
echo "Appium: $(appium --version)"
echo "Appium server basladilir -> http://127.0.0.1:4723"
echo "(dayandirmaq ucun Ctrl+C)"

exec appium --address 127.0.0.1 --port 4723
