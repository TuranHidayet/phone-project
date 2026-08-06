#!/usr/bin/env bash
# Serverde/cron-da avtomatik islemek ucun sarma skript.
# Numune cron (her saat basi):
#   0 * * * * /Users/a1234/phone-project/scripts/run_bot.sh telefon >> /Users/a1234/phone-project/logs/bot.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh

QUERY="${1:-telefon}"
PHONE_IP="${PHONE_IP:-192.168.1.127:5555}"

# Wi-Fi baglantisi dusubse yeniden qosulur (telefon reboot olmayibsa isleyir)
"$ANDROID_HOME/platform-tools/adb" connect "$PHONE_IP" >/dev/null 2>&1 || true

echo "=== $(date '+%F %T') | sorgu: $QUERY ==="
$PY src/brave_google_bot.py "$QUERY" --udid "$PHONE_IP"
