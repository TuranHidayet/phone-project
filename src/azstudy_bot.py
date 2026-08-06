#!/usr/bin/env python3
"""
AzStudy botu (REAL Android, chromedriver YOXDUR)
------------------------------------------------
Google-da "xaricde tehsil" axtarir -> neticelerde azstudy.az-i tapib
REAL barmaqla acir -> saytda verilen muddet qeder (default 90 san) gezir:
scroll edir, daxili sehifelere kecir -> sonda izleri silir, tabi baglayir.

AZSTUDY.AZ NECE TAPILIR:
  Google neticeleri arasinda oz saytimizi tapmaq ucun Brave-in oz
  "Find in page" funksiyasi istifade olunur: "azstudy" yazilir, tapilan yer
  NARINCI isiqlanir. Ekran seklinden hemin narinci zolagin yeri tapilir ve
  ora toxunulur (sag kenardaki scrollbar gostericisi istisna edilir).
  Isiqlanma sehifenin harasinda olursa olsun taplir -- scroll lazim deyil,
  cunki Find in page ozu oraya surusdurur.

Istifade:
    source scripts/env.sh
    $PY src/azstudy_bot.py
    $PY src/azstudy_bot.py --stay 120 --query "xaricde tehsil"
"""

import os
import re
import sys
import time
import random
import shutil
import argparse
import tempfile
import subprocess
from urllib.parse import quote_plus

from android_chrome_bot import (
    find_adb, adb_sh, detect_devices, device_profile, touch_scroll, log,
)
from brave_google_bot import (
    BRAVE_PKG, screencap, current_url, ui_dump, node_center, human_tap,
    open_url, close_bot_tab, clear_browsing_data,
)

SITE_MARK = "azstudy"                      # neticelerde axtarilan soz
SITE_HOST = "azstudy.az"

# Gezinti ucun daxili sehifeler (biri-ikisi tesadufi secilir)
SITE_PAGES = [
    "https://azstudy.az/turkiyede-tehsil-haqqi/",
    "https://azstudy.az/turkiye-universitetleri/",
    "https://azstudy.az/rusiyada-tehsil-2025/",
    "https://azstudy.az/rusiyada-pulsuz-tehsil-2025/",
    "https://azstudy.az/dim-turkiye/",
]

# Find in page isiqlanmasinin rengi (narinci)
HL_MIN_R, HL_G_LO, HL_G_HI, HL_MAX_B = 220, 120, 210, 110


def open_find_in_page(adb, serial, tag, text):
    """Menyu -> Find in page -> metni yazir. Ugurda find_status qaytarir ("1/1")."""
    xml = ui_dump(adb, serial)
    menu = node_center(xml, r'resource-id="[^"]*id/menu_button"')
    if not menu:
        return None
    human_tap(adb, serial, *menu)
    time.sleep(2.5)

    xml = ui_dump(adb, serial)
    fip = node_center(xml, r'text="Find in page"')
    if not fip:
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        return None
    human_tap(adb, serial, *fip)
    time.sleep(2)

    adb_sh(adb, serial, "shell", "input", "text", text)
    time.sleep(3.5)

    xml = ui_dump(adb, serial)
    for chunk in xml.split("<node")[1:]:
        if "find_status" in chunk:
            m = re.search(r'text="([^"]*)"', chunk)
            if m:
                return m.group(1).strip()
    return ""


def find_highlight(png_path, size):
    """
    Ekran seklinde narinci Find-in-page isiqlanmasini tapir.
    Sag kenar (scrollbar gostericisi) ve yuxari panel istisna edilir.
    Qaytarir: (x, y) merkez ve ya None.
    """
    from PIL import Image
    im = Image.open(png_path).convert("RGB")
    w, h = im.size
    px = im.load()
    x_max = int(w * 0.85)              # scrollbar gostericisi sag kenardadir
    hits = []
    for y in range(200, h - 100, 2):
        for x in range(8, x_max, 2):
            r, g, b = px[x, y]
            if r > HL_MIN_R and HL_G_LO < g < HL_G_HI and b < HL_MAX_B:
                hits.append((x, y))
    if len(hits) < 30:
        return None
    xs = [p[0] for p in hits]
    ys = [p[1] for p in hits]
    return (sum(xs) // len(xs), sum(ys) // len(ys))


def stable_highlight(adb, serial, size, shot, tag):
    """
    Isiqlanmani tapir ve sehifenin SABIT oldugunu gozleyir: iki ardicil
    ekran seklinde eyni yerde olanda qaytarir (sekil yuklenmesi sehifeni
    surusdurur -- yoxsa toxunus sehv karta duse biler).
    """
    prev = None
    for _ in range(5):
        if not screencap(adb, serial, shot):
            return None
        hl = find_highlight(shot, size)
        if hl and prev and abs(hl[0] - prev[0]) < 12 and abs(hl[1] - prev[1]) < 12:
            return hl
        prev = hl
        time.sleep(1.5)
    return prev


def dismiss_popups(adb, serial, tag):
    """Translate ve bu kimi teklif pencerelerini baglayir."""
    xml = ui_dump(adb, serial)
    if "Translate page" in xml or "infobar" in xml:
        btn = node_center(xml, r'resource-id="[^"]*infobar_close_button"')
        if not btn:
            btn = node_center(xml, r'text="(No thanks|Xeyr)"')
        if btn:
            human_tap(adb, serial, *btn)
            time.sleep(1.2)
            log(tag, "   (translate teklifi baglandi)")


def browse_site(adb, serial, size, tag, total_secs):
    """
    Saytda total_secs qeder gezir: evvel dusdukleri sehifede scroll,
    sonra 1-2 daxili sehifeye kecib orada da scroll edir.
    """
    t_end = time.time() + total_secs
    pages = random.sample(SITE_PAGES, k=2)
    # vaxt 3 hisseye bolunur: dusdukleri sehife + 2 daxili sehife
    marks = [t_end - total_secs * 2 / 3, t_end - total_secs / 3]
    page_i = 0

    log(tag, f"Saytda gezinti baslayir ({total_secs:.0f} san)...")
    while time.time() < t_end:
        touch_scroll(adb, serial, size, steps=1)
        time.sleep(random.uniform(1.5, 3.5))
        if page_i < len(marks) and time.time() >= marks[page_i]:
            nxt = pages[page_i]
            log(tag, f"-> daxili sehife: {nxt}")
            open_url(adb, serial, BRAVE_PKG, nxt)
            time.sleep(random.uniform(5, 7))
            dismiss_popups(adb, serial, tag)
            page_i += 1
    log(tag, "Gezinti bitdi.")


def main():
    p = argparse.ArgumentParser(description="AzStudy botu (Google -> azstudy.az -> gezinti)")
    p.add_argument("--query", default="xaricde tehsil", help="Google axtaris sozu")
    p.add_argument("--stay", type=float, default=90,
                   help="Saytda toplam nece saniye gezsin (default 90)")
    p.add_argument("--udid", help="Cihaz serial / IP:port")
    p.add_argument("--keep-tab", action="store_true",
                   help="Sonda tabi baglama (default: baglanir)")
    p.add_argument("--keep-data", action="store_true",
                   help="Sonda brauzer izlerini silme (default: silinir)")
    args = p.parse_args()

    adb = find_adb()
    if not adb:
        print("XETA: adb tapilmadi. `source scripts/env.sh` et.")
        sys.exit(1)

    ready, problems = detect_devices(adb)
    for s, st in problems:
        print(f"XEBERDARLIQ: {s} -> '{st}'")
    if not ready:
        print("XETA: qosulu cihaz yoxdur.")
        sys.exit(1)

    serial = args.udid or ready[0]
    if serial not in ready:
        print(f"XETA: {serial} hazir deyil. Qosulular: {', '.join(ready)}")
        sys.exit(1)

    if BRAVE_PKG not in adb_sh(adb, serial, "shell", "pm", "list", "packages", BRAVE_PKG):
        print(f"XETA: Brave ({BRAVE_PKG}) telefonda yoxdur.")
        sys.exit(1)

    prof = device_profile(adb, serial)
    tag = prof["model"] or serial
    size = prof["size"]
    print(f"=== {prof['model']} | Android {prof['android']} | {size[0]}x{size[1]} | Brave ===\n")

    shots = tempfile.mkdtemp(prefix="azstudybot-")
    shot = os.path.join(shots, "fip.png")

    def bail(code, *msgs):
        for m in msgs:
            log(tag, m)
        last = os.path.join(tempfile.gettempdir(), "azstudybot-last.png")
        try:
            shutil.copy(shot, last)
            log(tag, f"   Son ekran sekli: {last}")
        except Exception:
            pass
        shutil.rmtree(shots, ignore_errors=True)
        sys.exit(code)

    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
    adb_sh(adb, serial, "shell", "wm", "dismiss-keyguard")

    url = f"https://www.google.com/search?q={quote_plus(args.query)}"
    log(tag, f"Brave acilir, axtarilir: '{args.query}'")
    open_url(adb, serial, BRAVE_PKG, url)
    time.sleep(random.uniform(9, 12))

    cur = current_url(adb, serial)
    if "/sorry" in cur or "recaptcha" in cur.lower():
        bail(2, "!! Google bot yoxlamasi (CAPTCHA) cixdi -- dayanilir.")

    # azstudy neticesini Find in page ile tap; sehv karta dususde tekrar cehd
    after = ""
    for attempt in range(1, 3 + 1):
        status = open_find_in_page(adb, serial, tag, SITE_MARK)
        if status is None:
            bail(1, "!! Find in page acila bilmedi.")
        if status in ("", "0/0"):
            bail(1, f"!! '{SITE_MARK}' neticelerde tapilmadi (status: {status or '?'}).",
                 "   Sayt bu sorgu ucun ilk yuklenen neticelerde yoxdur.")
        log(tag, f"'{SITE_MARK}' neticede tapildi (status: {status}), isiqlanma axtarilir...")

        hl = stable_highlight(adb, serial, size, shot, tag)
        if not hl:
            bail(1, "!! Narinci isiqlanma ekranda tapilmadi.")

        log(tag, f"-> azstudy neticesine toxunulur ({hl[0]},{hl[1]})")
        human_tap(adb, serial, *hl)
        time.sleep(random.uniform(6, 9))
        dismiss_popups(adb, serial, tag)

        after = current_url(adb, serial)
        if SITE_HOST not in after:
            time.sleep(4)
            after = current_url(adb, serial)
        if SITE_HOST in after:
            break
        log(tag, f"   sehv sehife acildi ({after or '?'}) -- SERP-e qayidilir "
                 f"(cehd {attempt}/3)")
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(random.uniform(4, 6))

    log(tag, f"AÇILDI: {after or '(unvan oxunmadi)'}")
    if SITE_HOST not in after:
        log(tag, f"XEBERDARLIQ: unvanda {SITE_HOST} gorunmur, gezinti yene de davam edir.")

    browse_site(adb, serial, size, tag, args.stay)

    shutil.rmtree(shots, ignore_errors=True)

    if not args.keep_data:
        clear_browsing_data(adb, serial, tag)
    if not args.keep_tab:
        close_bot_tab(adb, serial, BRAVE_PKG, tag)
    log(tag, "Bitdi ✅")


if __name__ == "__main__":
    main()
