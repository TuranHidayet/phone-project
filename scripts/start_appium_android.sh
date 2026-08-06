#!/usr/bin/env bash
# Android ucun Appium serverini ise salir (sudo TELEB OLUNMUR, tunnel de lazim deyil).
# Bu pencereni aciq saxla.
set -e

cd "$(dirname "$0")/.."
source scripts/env.sh

echo "Node:   $(node --version)"
echo "Appium: $(appium --version)"
echo "adb:    $(adb version | head -1)"
# iOS serveri 4723-de qalir; Android ucun ayri port -> ikisi yan-yana isleye biler
PORT="${APPIUM_PORT:-4724}"
echo "Appium server basladilir -> http://127.0.0.1:$PORT"
echo "(dayandirmaq ucun Ctrl+C)"

# chromedriver_autodownload: Chrome versiyasina uygun driver-i Appium ozu yuklesin
exec appium --address 127.0.0.1 --port "$PORT" \
  --allow-insecure=uiautomator2:chromedriver_autodownload
