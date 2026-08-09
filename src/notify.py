#!/usr/bin/env python3
"""
Telegram bildirisleri (xarici kitabxana YOXDUR -- yalniz urllib).

QURASDIRMA (token bu fayla YAZILMIR, ayrica konfiqde saxlanir):
    ~/.config/azstudy/telegram.env
        TELEGRAM_TOKEN=123456:AA...
        TELEGRAM_CHAT_ID=123456789
Fayl yoxdursa ve ya bos qalibsa butun funksiyalar SESSIZ isleyir --
bot bildirissiz normal davam edir (bildiris ucun proses dayanmamalidir).

Istifade:
    from notify import send, configured
    send("Bot basladi")
"""

import os
import json
import time
import urllib.parse
import urllib.request

CONFIG_PATH = os.path.expanduser("~/.config/azstudy/telegram.env")
API = "https://api.telegram.org/bot{token}/sendMessage"


def _load_config():
    """Once mühit deyiskenleri, sonra konfiq fayli. Token kodda saxlanmir."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        return token, chat

    try:
        with open(CONFIG_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "TELEGRAM_TOKEN" and not token:
                    token = v
                elif k == "TELEGRAM_CHAT_ID" and not chat:
                    chat = v
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return token, chat


def configured():
    token, chat = _load_config()
    return bool(token and chat)


def send(text, silent=False, retries=2):
    """
    Telegram-a mesaj gonderir. Ugur/ugursuzluq bool qaytarir.
    Sebekede problem olsa da CAGIRAN PROSES DAYANMIR -- xetalar udulur.
    """
    token, chat = _load_config()
    if not (token and chat):
        return False

    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text[:4000],           # Telegram limiti 4096
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "disable_notification": "true" if silent else "false",
    }).encode()

    url = API.format(token=token)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode()).get("ok", False)
        except Exception:
            if attempt < retries:
                time.sleep(2 + attempt * 3)
    return False


if __name__ == "__main__":
    import sys
    msg = " ".join(sys.argv[1:]) or "AzStudy bot: test mesaji ✅"
    if not configured():
        print(f"Telegram qurasdirilmayib. Konfiq: {CONFIG_PATH}")
        sys.exit(2)
    print("gonderildi" if send(msg) else "GONDERILMEDI (token/chat_id yanlis ola biler)")
