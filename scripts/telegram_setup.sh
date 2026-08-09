#!/usr/bin/env bash
# Telegram bildirisleri ucun konfiq faylini hazirlayir.
#
# TOKEN BURADA SAXLANMIR ve git-e DUSMUR -- ayrica fayla yazilir:
#   ~/.config/azstudy/telegram.env   (icaze: yalniz sahibi oxuya bilir)
#
# Addimlar:
#   1) Telegram-da @BotFather -> /newbot -> bot adini ver -> TOKEN alacaqsan
#   2) Oz botunla sohbeti ac ve ona bir mesaj yaz (ilk mesaj vacibdir!)
#   3) Bu skripti ise sal: scripts/telegram_setup.sh
#      Token soruşacaq (ekranda gorunmeyecek), chat_id-ni OZU tapacaq.
set -uo pipefail

CFG_DIR="$HOME/.config/azstudy"
CFG="$CFG_DIR/telegram.env"
mkdir -p "$CFG_DIR"

echo "=== Telegram bildiris qurasdirmasi ==="
echo
if [ -f "$CFG" ]; then
    echo "Konfiq artiq var: $CFG"
    printf "Ustunden yazilsin? (h/y) "
    read -r ans
    [ "$ans" = "h" ] || [ "$ans" = "H" ] || { echo "dayandirildi."; exit 0; }
fi

printf "BotFather-dan aldigin TOKEN (ekranda gorunmeyecek): "
stty -echo 2>/dev/null; read -r TOKEN; stty echo 2>/dev/null; echo
TOKEN=$(printf '%s' "$TOKEN" | tr -d '[:space:]')
[ -z "$TOKEN" ] && { echo "XETA: token bos."; exit 1; }

# BotFather tokeni "123456789:AAH..." formatindadir -- sehv yapisdirmani
# fayla yazmadan EVVEL tuturuq
if ! printf '%s' "$TOKEN" | grep -qE '^[0-9]{6,}:[A-Za-z0-9_-]{30,}$'; then
    echo "XETA: token formati duz gorunmur."
    echo "      Gozlenilen: 123456789:AAH... (reqemler, iki noqta, uzun hisse)"
    echo "      BotFather-dakı mesajdan TAM kopyala (bosluqsuz)."
    exit 1
fi

echo "Token yoxlanilir..."
ME=$(curl -s --max-time 15 "https://api.telegram.org/bot$TOKEN/getMe")
if ! printf '%s' "$ME" | grep -q '"ok":true'; then
    echo "XETA: Telegram tokeni qebul etmedi (yanlis ve ya legv edilmis)."
    echo "      BotFather-da /mybots -> API Token ile yeniden yoxla."
    exit 1
fi
BOTNAME=$(printf '%s' "$ME" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')
echo "Bot tapildi: @$BOTNAME"

echo "chat_id axtarilir (botuna yazdigin mesaj oxunur)..."
CHAT=$(curl -s --max-time 15 "https://api.telegram.org/bot$TOKEN/getUpdates" \
       | sed -n 's/.*"chat":{"id":\(-\{0,1\}[0-9]\{1,\}\).*/\1/p' | head -1)

if [ -z "$CHAT" ]; then
    echo
    echo "chat_id tapilmadi -- bu, hele bota mesaj yazmadigin demekdir."
    echo "Telegram-da @$BOTNAME botunu ac, ona /start yaz, sonra bu skripti"
    echo "tekrar ise sal. (Token duzdur, sadece mesaj lazimdir.)"
    exit 1
fi

umask 077
cat > "$CFG" <<EOF
# AzStudy bot bildirisleri -- bu fayl git-e DUSMUR
TELEGRAM_TOKEN=$TOKEN
TELEGRAM_CHAT_ID=$CHAT
EOF
chmod 600 "$CFG"

echo "chat_id tapildi: $CHAT"
echo "Konfiq yazildi: $CFG (icaze 600)"
echo
cd "$(dirname "$0")/.."
source scripts/env.sh
echo "Test mesaji gonderilir..."
$PY src/notify.py "🤖 AzStudy bot bildirisleri qosuldu. Bundan sonra xetalar ve gunluk hesabat buraya gelecek."
