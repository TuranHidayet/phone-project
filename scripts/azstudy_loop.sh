#!/usr/bin/env bash
# AzStudy botunu 4 deqiqelik DOVRLE isledir:
#   - bot islenir (adeten ~3 deq 20 san)
#   - dovrun qalan vaxti gozlenilir (bufer)
#   - 4 deqiqe tamamlananda yeni dovr baslayir
#   - bot 4 deqiqeden UZUN cekerse, bitdiyi anda derhal yeni dovr baslayir
#
# Baslatmaq:  nohup scripts/azstudy_loop.sh >> logs/azstudy_loop.log 2>&1 &
# Dayandirmaq: scripts/azstudy_loop.sh stop
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh

PIDFILE="logs/azstudy_loop.pid"
CYCLE="${CYCLE:-240}"          # dovrun uzunlugu (saniye)
PHONE_IP="${PHONE_IP:-192.168.1.127:5555}"

if [ "${1:-}" = "stop" ]; then
    if [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null; then
        rm -f "$PIDFILE"
        echo "dayandirildi."
    else
        rm -f "$PIDFILE"
        echo "isleyen dovr tapilmadi."
    fi
    exit 0
fi

# eyni anda iki loop islemesin
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "XETA: loop artiq isleyir (pid $(cat "$PIDFILE")). Once: scripts/azstudy_loop.sh stop"
    exit 1
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

mkdir -p logs
n=0
while true; do
    n=$((n + 1))
    t0=$(date +%s)
    echo "=== $(date '+%F %T') | dovr #$n baslayir ==="

    # Wi-Fi baglantisi dusubse yeniden qosulur
    "$ANDROID_HOME/platform-tools/adb" connect "$PHONE_IP" >/dev/null 2>&1 || true

    $PY src/azstudy_bot.py --udid "$PHONE_IP"
    rc=$?
    el=$(( $(date +%s) - t0 ))
    echo "=== $(date '+%F %T') | dovr #$n bitdi (kod=$rc, ${el} san) ==="

    if [ "$el" -lt "$CYCLE" ]; then
        w=$(( CYCLE - el ))
        echo "    novbeti dovre qeder $w san bufer..."
        sleep "$w"
    else
        echo "    dovr ${CYCLE} san-dan uzun cekdi -- derhal novbeti dovr"
    fi
done
