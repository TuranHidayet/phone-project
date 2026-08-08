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
CYCLE="${CYCLE:-300}"          # dovrun uzunlugu (saniye) -- bir is ~4 deq 40 san

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

    # Telefonlari tap (IP deyisibse ozu axtarir, sonradan qosulani da goturur)
    SERIALS=$(scripts/find_phone.sh 2>/dev/null || true)
    if [ -z "$SERIALS" ]; then
        echo "    telefon tapilmadi (sonduruludur / Wi-Fi-da deyil) -- bu dovr atlanir"
        rc=90
    else
        n=$(echo "$SERIALS" | grep -c .)
        echo "    $n telefon: $(echo $SERIALS | tr '\n' ' ')"
        # Her telefon ucun bot PARALEL isleyir -- ardicil olsa 2 telefon
        # dovr uzunluguna sigmazdi (bir is ~3 deq 30 san).
        pids=""
        for s in $SERIALS; do
            $PY src/azstudy_bot.py --udid "$s" &
            pids="$pids $!"
        done
        rc=0
        for p in $pids; do
            wait "$p" || rc=$?
        done
    fi
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
