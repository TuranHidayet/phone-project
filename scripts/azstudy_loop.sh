#!/usr/bin/env bash
# AzStudy botunu DOVRLE isledir (default 5 deqiqe):
#   - qosulu HER telefon ucun bot paralel islenir (bir is ~3 deq 30 san)
#   - dovrun qalan vaxti gozlenilir (bufer)
#   - dovr uzunlugu tamamlananda yeni dovr baslayir
#   - is CYCLE-den UZUN cekerse, bitdiyi anda derhal yeni dovr baslayir
#
# Telegram bildirisleri (qurasdirilibsa -- scripts/telegram_setup.sh):
#   loop basladi / dayandi, telefon itdi / qayitdi, ust-uste xetalar.
#   Her ugurlu is ucun mesaj GONDERILMIR (gunde ~300 mesaj olardi);
#   gunluk hesabat ayrica agentle saat 23:00-da gedir.
#
# Baslatmaq:  nohup scripts/azstudy_loop.sh >> logs/azstudy_loop.log 2>&1 &
# Dayandirmaq: scripts/azstudy_loop.sh stop
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh

PIDFILE="logs/azstudy_loop.pid"
CYCLE="${CYCLE:-300}"          # dovrun uzunlugu (saniye)

tg () {  # Telegram-a mesaj (qurasdirilmayibsa sessiz kecir)
    $PY src/notify.py "$1" >/dev/null 2>&1 || true
}

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

# Loop hansisa sebebden dayanarsa (kill, xeta, komputer sondurulmesi)
# Telegram-a xeber gedir. launchd onu yeniden baslatdiqda "basladi" mesaji gelir.
on_exit () {
    rm -f "$PIDFILE"
    tg "🛑 <b>AzStudy loop dayandı</b>
Son dövr: #${n:-0}. Yenidən başlamazsa yoxla:
launchctl list | grep azstudy"
}
trap on_exit EXIT

mkdir -p logs
tg "🔄 <b>AzStudy loop başladı</b>
Dövr: hər $((CYCLE / 60)) dəqiqə"

n=0
fails=0
phones_missing=0
prev_end=$(date +%s)
last_serials=""
while true; do
    n=$((n + 1))
    t0=$(date +%s)

    # FASILE ASKARLAMASI: komputer yatanda (qapaq baglananda) bu proses
    # oldurulmur, sadece DONUR -- oyananda davam edir. Yeni proses
    # baslamadigi ucun "dayandi/basladi" mesajlari da gelmir, halbuki
    # arada saatlarla is dayanmis ola biler. Ona gore iki dovr arasindaki
    # real fasileni olcub ozumuz xeber veririk.
    gap=$(( t0 - prev_end ))
    if [ "$gap" -gt $(( CYCLE * 2 )) ]; then
        tg "▶️ <b>İş bərpa olundu</b>
Fasilə: <b>$(( gap / 60 )) dəqiqə</b> (təxminən $(( gap / CYCLE )) dövr buraxıldı).
Səbəb: kompüter yatmışdı, şəbəkə kəsilmişdi və ya proses dayanmışdı."
        echo "    XEBERDARLIQ: $(( gap / 60 )) deqiqe fasile askarlandi"
    fi

    echo "=== $(date '+%F %T') | dovr #$n baslayir ==="

    # Telefonlari tap (IP deyisibse ozu axtarir, sonradan qosulani da goturur)
    SERIALS=$(scripts/find_phone.sh 2>/dev/null || true)
    if [ -z "$SERIALS" ]; then
        echo "    telefon tapilmadi (sonduruludur / Wi-Fi-da deyil) -- bu dovr atlanir"
        rc=90
        # Bildiris yalniz VEZIYYET DEYISENDE gedir (her dovrde spam olmasin)
        if [ "$phones_missing" -eq 0 ]; then
            tg "⚠️ <b>Telefon tapılmadı</b>
Cihaz söndürülüb, Wi-Fi-dan düşüb və ya batareya bitib.
Dövrlər telefon qayıdana qədər atlanacaq."
        fi
        phones_missing=$((phones_missing + 1))
    else
        cnt=$(echo "$SERIALS" | grep -c .)
        flat=$(echo $SERIALS | tr '\n' ' ')
        echo "    $cnt telefon: $flat"

        # Cihazin unvani deyisibse xeber ver -- bu gun IP iki defe deyisdi
        # (192.168.31.36 -> 192.168.1.134), sebebi anlamaq ucun faydalidir.
        if [ -n "$last_serials" ] && [ "$flat" != "$last_serials" ]; then
            tg "📶 <b>Cihaz ünvanı dəyişdi</b>
əvvəl: $last_serials
indi: $flat"
        fi
        last_serials="$flat"

        if [ "$phones_missing" -gt 0 ]; then
            tg "✅ <b>Telefon qayıtdı</b>
$cnt cihaz qoşuludur, dövrlər davam edir ($phones_missing dövr atlanmışdı)."
            phones_missing=0
        fi

        # Her telefon ucun bot PARALEL isleyir -- ardicil olsa 2 telefon
        # dovr uzunluguna sigmazdi.
        pids=""
        for s in $SERIALS; do
            $PY src/azstudy_bot.py --udid "$s" &
            pids="$pids $!"
        done
        rc=0
        for p in $pids; do
            wait "$p" || rc=$?
        done

        # Ust-uste xetalar: her xeta ucun bot ozu mesaj gonderir, burada ise
        # yalniz DAVAMLI problem halinda (3 dovr ardicil) xeberdarliq edirik.
        if [ "$rc" -ne 0 ]; then
            fails=$((fails + 1))
            if [ "$fails" -eq 3 ]; then
                tg "🔁 <b>Ardıcıl 3 dövr xəta ilə bitdi</b>
Problem davam edir — loglara bax:
logs/azstudy_loop.log"
            fi
        else
            if [ "$fails" -ge 3 ]; then
                tg "✅ <b>Bərpa olundu</b>
$fails uğursuz dövrdən sonra bot yenidən normal işləyir."
            fi
            fails=0
        fi
    fi
    prev_end=$(date +%s)
    el=$(( prev_end - t0 ))
    echo "=== $(date '+%F %T') | dovr #$n bitdi (kod=$rc, ${el} san) ==="

    if [ "$el" -lt "$CYCLE" ]; then
        w=$(( CYCLE - el ))
        echo "    novbeti dovre qeder $w san bufer..."
        sleep "$w"
    else
        echo "    dovr ${CYCLE} san-dan uzun cekdi -- derhal novbeti dovr"
    fi
done
