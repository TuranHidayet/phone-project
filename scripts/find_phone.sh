#!/usr/bin/env bash
# Telefonu tapib adb-ye qosur ve serialini cap edir.
#
# NIYE LAZIMDIR: telefonun IP-si (ve hetta ev sebekesinin alt sebekesi)
# deyise bilir -- mes. 192.168.1.127 -> 192.168.31.x. Sabit IP yazilmis
# skript bu halda "cihaz yoxdur" deyib dayanirdi. Burada ardicilliq belədir:
#   1) USB / artiq qosulu cihaz
#   2) yadda saxlanmis son IP (logs/phone_ip)
#   3) cari alt sebekede 5555 portunun taranmasi
# Tapilan IP yadda saxlanir ki, novbeti defe tarama lazim olmasin.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh

ADB="$ANDROID_HOME/platform-tools/adb"
IPFILE="logs/phone_ip"
mkdir -p logs

ready_serial () {
    "$ADB" devices | awk '$2=="device" {print $1; exit}'
}

# 1) artiq qosuludur (USB ve ya evvelki seans)
s=$(ready_serial)
[ -n "$s" ] && { echo "$s"; exit 0; }

# 2) yadda saxlanmis son IP
if [ -f "$IPFILE" ]; then
    last=$(cat "$IPFILE")
    "$ADB" connect "$last" >/dev/null 2>&1
    sleep 2
    s=$(ready_serial)
    [ -n "$s" ] && { echo "$s"; exit 0; }
fi

# 3) cari alt sebekeni tara (5555 portu aciq olan cihaz)
base=$(ifconfig 2>/dev/null | awk '/inet 192\.168\./ {print $2}' | head -1 | cut -d. -f1-3)
[ -z "$base" ] && exit 1

found=""
for i in $(seq 2 254); do
    ( nc -z -G 1 "$base.$i" 5555 >/dev/null 2>&1 && echo "$base.$i" ) &
done > /tmp/_phonescan.$$ 2>/dev/null
wait 2>/dev/null
found=$(head -1 /tmp/_phonescan.$$ 2>/dev/null)
rm -f /tmp/_phonescan.$$

[ -z "$found" ] && exit 1
"$ADB" connect "$found:5555" >/dev/null 2>&1
sleep 2
s=$(ready_serial)
[ -z "$s" ] && exit 1
echo "$found:5555" > "$IPFILE"
echo "$s"
