#!/usr/bin/env bash
# AzStudy botunu DOVRLE isledir (default 4 deqiqe):
#   - qosulu HER telefon ucun bot paralel islenir (bir is ~3 deq 30 san)
#   - dovrun qalan vaxti gozlenilir (bufer)
#   - dovr uzunlugu tamamlananda yeni dovr baslayir
#   - is CYCLE-den UZUN cekerse, bitdiyi anda derhal yeni dovr baslayir
#
# Telegram bildirisleri (qurasdirilibsa -- scripts/telegram_setup.sh):
#   loop basladi / dayandi, telefon itdi / qayitdi, ust-uste xetalar.
#   Her ugurlu is ucun mesaj GONDERILMIR (gunde ~360 mesaj olardi);
#   gunluk hesabat ayrica agentle saat 23:00-da gedir.
#
# Baslatmaq:  nohup scripts/azstudy_loop.sh >> logs/azstudy_loop.log 2>&1 &
# Dayandirmaq: scripts/azstudy_loop.sh stop
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh

PIDFILE="logs/azstudy_loop.pid"
CYCLE="${CYCLE:-240}"          # dovrun uzunlugu (saniye) -- bir dovr median 215 san
JOB_TIMEOUT="${JOB_TIMEOUT:-330}"   # bir telefonun isi ucun ust hedd (normal is 200-280 san)
FIND_TIMEOUT="${FIND_TIMEOUT:-90}"  # telefon kesfi ucun ust hedd (normal 3-15 san)

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
    #
    # Kesfe de VAXT LIMITI lazimdir: find_phone.sh her cihazda
    # `adb shell getprop ro.serialno` isledir. Telefon donarsa (adb "device"
    # gosterir, amma adbd cavab vermir) hemin cagiris sonsuz gozleyir ve dovr
    # hec baslamir. Limit asilanda kesf oldurulur, dovr atlanir, novbeti
    # dovrde yeniden cehd edilir.
    fp_out=$(mktemp)
    scripts/find_phone.sh > "$fp_out" 2>/dev/null &
    fp=$!
    ( sleep "$FIND_TIMEOUT"
      if kill -0 "$fp" 2>/dev/null; then
          echo "    XEBERDARLIQ: kesf ${FIND_TIMEOUT} san-de bitmedi -- dayandirilir"
          kill -9 "$fp" 2>/dev/null
      fi ) &
    fg=$!
    wait "$fp" 2>/dev/null
    # `wait` ELAVE EDILIB: sadece `kill` edende bash oldurulmus fon isini
    # loga "Terminated: ..." setri kimi yazir ve her dovrde skriptin oz kodu
    # loga dusurdu. `wait` prosesi sessizce yigisdirir.
    kill "$fg" 2>/dev/null
    wait "$fg" 2>/dev/null || true
    SERIALS=$(cat "$fp_out" 2>/dev/null || true)
    rm -f "$fp_out"
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
        #
        # VAXT LIMITI (gozetci): telefon donarsa (adb port aciq qalir, ping
        # kecir, amma adbd cavab vermir -- Redmi 8-de yasandi) bot sonsuza
        # qeder gozleyir. Asagidaki `wait` BUTUN botlari gozledigi ucun bir
        # donmus telefon dovru tamamile bloklayirdi: qalan telefonlar isini
        # bitirse de dovr baglanmirdi ve loop saatlarla dayanirdi.
        # Indi her bota gozetci qosulur -- limiti asan bot oldurulur, dovr
        # davam edir, hemin telefon novbeti dovrde yeniden yoxlanilir.
        pids=""
        guards=""
        for s in $SERIALS; do
            $PY src/azstudy_bot.py --udid "$s" &
            bp=$!
            pids="$pids $bp"
            ( sleep "$JOB_TIMEOUT"
              if kill -0 "$bp" 2>/dev/null; then
                  echo "    XEBERDARLIQ: $s ${JOB_TIMEOUT} san-de bitmedi -- bot dayandirilir"
                  kill -9 "$bp" 2>/dev/null
              fi ) &
            guards="$guards $!"
        done
        rc=0
        for p in $pids; do
            wait "$p" || rc=$?
        done
        # Botlar normal bitibse gozetcileri legv edirik, yoxsa hər dövrdən
        # bos `sleep` prosesleri yigilib qalar.
        for g in $guards; do
            kill "$g" 2>/dev/null
            wait "$g" 2>/dev/null || true
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
