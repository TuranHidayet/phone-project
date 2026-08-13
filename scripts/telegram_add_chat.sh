#!/usr/bin/env bash
# Telegram bildirislerine YENI ALICI elave edir (qrup ve ya ayri sexs).
#
# NECE ISLEYIR: bot yalniz onunla EVVELCE elaqe qurmus chat-lara yaza biler.
# Ona gore:
#   - Qrup ucun: qrup yarat -> botu qrupa elave et -> qrupda "/start@botun_adi" yaz
#   - Ayri sexs ucun: hemin sexs botu acib "/start" yazsin
# Sonra bu skripti islet: bot son mesajlari oxuyur (getUpdates), tapdigi
# chat-lari sadalayir ve secdiyini konfiqe elave edir.
#
# Konfiq: ~/.config/azstudy/telegram.env -> TELEGRAM_CHAT_ID=id1,id2,...
set -uo pipefail
CONF="$HOME/.config/azstudy/telegram.env"
[ -f "$CONF" ] || { echo "XETA: $CONF yoxdur. Once: scripts/telegram_setup.sh"; exit 1; }

TOKEN=$(grep -E '^TELEGRAM_TOKEN=' "$CONF" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')
CUR=$(grep -E '^TELEGRAM_CHAT_ID=' "$CONF" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')
[ -n "$TOKEN" ] || { echo "XETA: konfiqde TELEGRAM_TOKEN yoxdur."; exit 1; }

echo "Hazirda bildiris gonderilen chat-lar: ${CUR:-(yoxdur)}"
echo
echo "Botun gorduyu son chat-lar axtarilir..."
RAW=$(curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates?limit=100&allowed_updates=%5B%22message%22%2C%22my_chat_member%22%5D")

LIST=$(printf '%s' "$RAW" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
seen = {}
for u in d.get("result", []):
    for key in ("message", "edited_message", "my_chat_member", "channel_post"):
        ch = (u.get(key) or {}).get("chat")
        if not ch:
            continue
        cid = str(ch.get("id"))
        title = ch.get("title") or " ".join(
            x for x in (ch.get("first_name"), ch.get("last_name")) if x) or ch.get("username") or "?"
        seen[cid] = f'"'"'{title} [{ch.get("type")}]'"'"'
for cid, name in seen.items():
    print(f"{cid}\t{name}")')

if [ -z "$LIST" ]; then
    cat <<'EOS'
Hec bir chat tapilmadi. Sebebi ve hell yolu:
  QRUP ucun:
    1) Telegram-da qrup yarat (mes. "AzStudy bildirisleri")
    2) Botu qrupa elave et (botun @adi ile axtar)
    3) QRUPDA bir mesaj yaz: /start@botun_adi
  AYRI SEXS ucun:
    Hemin sexs botu acib "/start" yazsin
Sonra bu skripti yeniden islet.
EOS
    exit 1
fi

echo "Tapilan chat-lar:"
i=0; declare -a IDS=()
while IFS=$'\t' read -r cid name; do
    i=$((i+1)); IDS+=("$cid")
    mark=""
    case ",$CUR," in *",$cid,"*) mark="  (artiq elave olunub)" ;; esac
    echo "  $i) $cid  $name$mark"
done <<< "$LIST"

echo
printf "Hansini elave edim? (nomre, bir necesi ucun vergul: 1,3 / bosdursa cixir): "
read -r ans
[ -z "$ans" ] && { echo "deyisiklik edilmedi."; exit 0; }

NEW="$CUR"
IFS=',' read -ra picks <<< "$ans"
for p in "${picks[@]}"; do
    p=$(echo "$p" | tr -d '[:space:]')
    idx=$((p-1))
    cid="${IDS[$idx]:-}"
    [ -z "$cid" ] && { echo "  ($p yanlisdir, atlanir)"; continue; }
    case ",$NEW," in
        *",$cid,"*) echo "  $cid artiq var" ;;
        *) NEW="${NEW:+$NEW,}$cid"; echo "  + $cid elave olundu" ;;
    esac
done

# konfiqi yenile (icaze 600 saxlanilir)
tmp=$(mktemp)
grep -v -E '^TELEGRAM_CHAT_ID=' "$CONF" > "$tmp"
echo "TELEGRAM_CHAT_ID=$NEW" >> "$tmp"
install -m 600 "$tmp" "$CONF"
rm -f "$tmp"
echo
echo "Yeni siyahi: $NEW"
echo "Test mesaji gonderilir..."
cd "$(dirname "$0")/.."
source scripts/env.sh
$PY src/notify.py "✅ Yeni alıcı əlavə olundu — bu mesaj bütün alıcılara getdi."
