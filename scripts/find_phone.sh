#!/usr/bin/env bash
# Qosulu telefonlari tapir, adb-ye qosur ve HER BIRININ serialini cap edir
# (her setirde bir serial).
#
# NIYE LAZIMDIR: telefonun IP-si (hetta ev sebekesinin alt sebekesi) deyise
# bilir -- mes. 192.168.1.127 -> 192.168.31.36. Sabit IP yazilmis skript bu
# halda "cihaz yoxdur" deyib dayanirdi. Ardicilliq belədir:
#   1) artiq qosulu cihazlar (USB / evvelki seans)
#   2) yadda saxlanmis IP-ler (logs/phone_ip -- her setirde biri)
#   3) cari alt sebekede 5555 portunun taranmasi (butun cihazlar)
# Tapilan IP-ler yadda saxlanir ki, novbeti defe tarama lazim olmasin.
#
# PHONES: gozlenilen telefon sayi (default 1). Qosulu cihaz sayi bundan azdirsa
# alt sebeke yeniden taranir -- beleliklə sonradan qosulan 2-ci telefon da tapilir.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh

ADB="$ANDROID_HOME/platform-tools/adb"
IPFILE="logs/phone_ip"
DISABLED="config/disabled_phones.txt"     # botun islemeyeceyi telefonlar
WANT="${PHONES:-1}"
mkdir -p logs

# Sondurulmus cihazlar: aparat seriali / satis adi / model kodu ile yazila biler
is_disabled () {   # $1=hw $2=ad $3=model
    [ -f "$DISABLED" ] || return 1
    local line
    while IFS= read -r line; do
        line=$(echo "$line" | sed 's/#.*//' | tr -d '[:space:]')
        [ -z "$line" ] && continue
        for v in "$1" "$2" "$3"; do
            [ -n "$v" ] || continue
            if [ "$(echo "$v" | tr -d '[:space:]' | tr 'A-Z' 'a-z')" = "$(echo "$line" | tr 'A-Z' 'a-z')" ]; then
                return 0
            fi
        done
    done < "$DISABLED"
    return 1
}

ready_serials () {
    # BIR CIHAZ BIR NECE ADLA gorune biler: IP:5555, IP:43997 (simsiz sazlama
    # portu) ve mDNS adi (adb-1023...._adb-tls-connect._tcp) -- hepsi eyni
    # telefondur. Deduplikasiya EDILMESE loop eyni telefonda 2-3 bot paralel
    # isledir ve onlar bir-birinin isini pozur.
    # Ona gore cihazin APARAT SERIALI (ro.serialno) ile teklesdirilir.
    # QEYD: `adb shell`-e `< /dev/null` VACIBDIR -- yoxsa o, dovrun stdin-ini
    # udur ve siyahi birinci cihazdan sonra kesilir.
    "$ADB" devices | awk '$2=="device" {print $1}' | while read -r s; do
        [ -n "$s" ] || continue
        hw=$("$ADB" -s "$s" shell getprop ro.serialno < /dev/null 2>/dev/null | tr -d '\r\n')
        [ -z "$hw" ] && hw="$s"
        nm=$("$ADB" -s "$s" shell getprop ro.product.marketname < /dev/null 2>/dev/null | tr -d '\r\n')
        md=$("$ADB" -s "$s" shell getprop ro.product.model < /dev/null 2>/dev/null | tr -d '\r\n')
        if is_disabled "$hw" "$nm" "$md"; then
            continue                     # config/disabled_phones.txt-de sondurulub
        fi
        # Ustunluk: sabit :5555 (yeniden baslatmadan sonra da eyni qalir) >
        # tesadufi simsiz-sazlama portu > mDNS adi
        case "$s" in
            *:5555) prio=0 ;;
            *:*)    prio=1 ;;
            *)      prio=2 ;;
        esac
        printf '%s\t%s\t%s\n' "$hw" "$prio" "$s"
    done | sort -k1,1 -k2,2n | awk -F'\t' '!seen[$1]++ {print $3}'
}

# Telefon Wi-Fi-dan dusende adb-de "offline" kimi ilisib qalir ve hemin
# kohne qeyd yeniden qosulmaga mane olur -- once onlari atiriq.
"$ADB" devices | awk '$2!="device" && $1 ~ /:/ {print $1}' | while read -r dead; do
    [ -n "$dead" ] && "$ADB" disconnect "$dead" >/dev/null 2>&1
done
ready_count () {
    ready_serials | grep -c . || true
}

# 1) artiq qosulu olanlar + 2) yadda saxlanmis IP-ler
#
# VACIB: `adb connect` cavab vermeyen unvanda ~40 SANIYE donur. Telefonun
# IP-si deyisende (ucus rejimi / DHCP) yadda saxlanmis unvanlar kohnelir ve
# kesf 80 saniyeye qalxirdi. Ona gore once `nc` ile port yoxlanilir (~1 san),
# yalniz aciq olanda adb cagirilir. Taramanin ozu cemi ~3 saniyedir.
if [ -f "$IPFILE" ]; then
    while read -r ip; do
        [ -n "$ip" ] || continue
        host="${ip%:*}"; port="${ip##*:}"
        if nc -z -G 1 "$host" "${port:-5555}" >/dev/null 2>&1; then
            "$ADB" connect "$ip" >/dev/null 2>&1
        fi
    done < "$IPFILE"
    sleep 2
fi

# 2.5) mDNS: "Simsiz sazlama" (Android 11+) ile qosulmus, ARTIQ QOSALASDIRILMIS
# (paired) cihazlar tesadufi portda reklam edir -- onlari adadan tapiriq.
# Bu halda kabel lazim olmur, amma port her yeniden baslatmada deyisir.
if [ "$(ready_count)" -lt "$WANT" ]; then
    "$ADB" mdns services 2>/dev/null \
        | awk '/_adb-tls-connect/ {print $NF}' \
        | while read -r hp; do
            [ -n "$hp" ] && "$ADB" connect "$hp" >/dev/null 2>&1
          done
    sleep 2
fi

# 3) sayi catmirsa alt sebekeni tara
if [ "$(ready_count)" -lt "$WANT" ]; then
    base=$(ifconfig 2>/dev/null | awk '/inet 192\.168\./ {print $2}' | head -1 | cut -d. -f1-3)
    if [ -n "$base" ]; then
        scan=$(mktemp)
        for i in $(seq 2 254); do
            ( nc -z -G 1 "$base.$i" 5555 >/dev/null 2>&1 && echo "$base.$i:5555" ) >> "$scan" &
        done
        wait 2>/dev/null
        if [ -s "$scan" ]; then
            sort -u "$scan" | while read -r ip; do
                "$ADB" connect "$ip" >/dev/null 2>&1
            done
            sleep 2
            sort -u "$scan" > "$IPFILE"
        fi
        rm -f "$scan"
    fi
fi

serials=$(ready_serials)
[ -z "$serials" ] && exit 1
echo "$serials"
