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
[ -z "$TOKEN" ] && { echo "XETA: token bos."; exit 1; }

echo "chat_id axtarilir (botuna yazdigin mesaj oxunur)..."
CHAT=$(curl -s --max-time 15 "https://api.telegram.org/bot$TOKEN/getUpdates" \
       | sed -n 's/.*"chat":{"id":\(-\{0,1\}[0-9]\{1,\}\).*/\1/p' | head -1)

if [ -z "$CHAT" ]; then
    echo
    echo "chat_id tapilmadi. Sebeb: hele botuna mesaj yazmamisan."
    echo "Telegram-da botunu ac, ona /start ve ya istenilen mesaj yaz, sonra"
    echo "bu skripti tekrar ise sal."
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
