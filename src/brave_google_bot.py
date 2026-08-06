#!/usr/bin/env python3
"""
Brave + Google axtaris botu (REAL Android, chromedriver YOXDUR)
---------------------------------------------------------------
Telefonda Brave-i acir -> Google-da axtarir -> neticelerden birincisine
REAL barmaqla toxunur -> acilan sehifede insan kimi gezir.

NIYE CHROMEDRIVER YOXDUR:
  chromedriver brauzeri "avtomatlasdirma rejiminde" isledir (navigator.webdriver
  ve s.) -- Google bunu goruб CAPTCHA cixarir. Burada ise her sey adb ile,
  emeliyyat sistemi seviyyesinde gedir: intent + real toxunus. Brauzer ucun bu,
  adi istifadeciden ferqlenmir.

NECE ISLEYIR:
  Brave veb mezmununu uiautomator-a acmir (yalniz brauzerin oz duymeleri gorunur),
  ona gore netice linkleri EKRAN SEKLINDEN tapilir: Google-un netice basliqlari
  xarakterik mavi rengdedir (#1558D6). Skript hemin rengden ibaret "metn zolaqlari"
  tapir, doldurulmus mavi duymeleri (mes. "Giris") sixliga gore atir.

Istifade:
    source scripts/env.sh
    $PY src/brave_google_bot.py telefon
    $PY src/brave_google_bot.py "telefon qiymetleri" --result 2 --stay 20
    $PY src/brave_google_bot.py telefon --udid 192.168.1.127:5555
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

BRAVE_PKG = "com.brave.browser"

# Google netice basliginin rengi (olculub: #1558D6)
LINK_RGB = (21, 88, 214)
RGB_TOL = 28            # renge dozumluluk
MIN_ROW_HITS = 18       # setirde en azi bu qeder mavi piksel olsun
MIN_BAND_H = 18         # zolagin hundurluyu (basliq metni boyukdur)
MIN_BAND_W = 140        # zolagin eni
MAX_DENSITY = 0.72      # bundan sixdirsa -> doldurulmus duymedir, metn deyil


def screencap(adb, serial, out_path):
    """Telefondan ekran sekli goturur (fayl telefonda saxlanmir)."""
    with open(out_path, "wb") as f:
        p = subprocess.run([adb, "-s", serial, "exec-out", "screencap", "-p"],
                           stdout=f, stderr=subprocess.DEVNULL)
    return p.returncode == 0 and os.path.getsize(out_path) > 1000


def current_url(adb, serial):
    """Brave-in unvan setrini oxuyur (uiautomator brauzerin oz UI-ni gosterir)."""
    adb_sh(adb, serial, "shell", "uiautomator", "dump", "/sdcard/_ui.xml")
    xml = adb_sh(adb, serial, "shell", "cat", "/sdcard/_ui.xml")
    cands = re.findall(r'text="([^"]{4,120})"', xml)
    for t in cands:
        if "/" in t and "." in t and " " not in t:
            return t
    return cands[0] if cands else ""


def find_link_bands(png_path, skip_top_frac=0.28):
    """
    Ekran seklinde mavi LINK METNI zolaqlarini tapir.
    Qaytarir: [(y_ust, y_alt, x_sol, x_sag), ...] -- yuxaridan asagi.
    """
    from PIL import Image
    im = Image.open(png_path).convert("RGB")
    w, h = im.size
    px = im.load()
    lr, lg, lb = LINK_RGB
    y0 = int(h * skip_top_frac)          # unvan setri / Google basligi atilir

    rows = []                            # (y, hits, xmin, xmax)
    for y in range(y0, int(h * 0.93), 2):
        hits, xmin, xmax = 0, w, 0
        for x in range(8, w - 8, 2):
            r, g, b = px[x, y]
            if abs(r - lr) < RGB_TOL and abs(g - lg) < RGB_TOL and abs(b - lb) < RGB_TOL:
                hits += 1
                if x < xmin:
                    xmin = x
                if x > xmax:
                    xmax = x
        rows.append((y, hits, xmin, xmax))

    bands, cur = [], None
    for y, hits, xmin, xmax in rows:
        if hits >= MIN_ROW_HITS // 2:    # /2 -- her 2-ci pikseli yoxlayiriq
            if cur is None:
                cur = [y, y, xmin, xmax, hits]
            else:
                cur[1] = y
                cur[2] = min(cur[2], xmin)
                cur[3] = max(cur[3], xmax)
                cur[4] += hits
        else:
            if cur is not None:
                bands.append(cur)
                cur = None
    if cur is not None:
        bands.append(cur)

    out = []
    for ytop, ybot, xl, xr, hits in bands:
        bh, bw = ybot - ytop, xr - xl
        if bh < MIN_BAND_H or bw < MIN_BAND_W:
            continue
        # sixliq: doldurulmus mavi duyme (mes. "Giris") vs metn
        density = hits / max(1, (bw / 2) * (bh / 2))
        if density > MAX_DENSITY:
            continue
        out.append((ytop, ybot, xl, xr))
    return out


def human_tap(adb, serial, x, y):
    adb_sh(adb, serial, "shell", "input", "tap", str(int(x)), str(int(y)))


def main():
    p = argparse.ArgumentParser(description="Brave + Google axtaris botu (adb, chromedriver-siz)")
    p.add_argument("query", nargs="?", default="telefon", help="Axtaris sozu")
    p.add_argument("--result", type=int, default=1, help="Necenci netice acilsin (default 1)")
    p.add_argument("--udid", help="Cihaz serial / IP:port")
    p.add_argument("--stay", type=float, default=15, help="Acilan sehifede nece saniye qalsin")
    p.add_argument("--shots", default=None,
                   help="Ekran sekillerini bu qovluqda SAXLA (default: saxlanmir, "
                        "muveqqeti fayl istifadeden sonra silinir)")
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

    # --shots verilibse sekiller qalir; verilmeyibse muveqqeti qovluqda isleyib silinir
    keep = args.shots is not None
    shots = args.shots if keep else tempfile.mkdtemp(prefix="bravebot-")
    if keep:
        os.makedirs(shots, exist_ok=True)

    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP")

    url = f"https://www.google.com/search?q={quote_plus(args.query)}"
    log(tag, f"Brave acilir, axtarilir: '{args.query}'")
    adb_sh(adb, serial, "shell", "am", "start", "-a", "android.intent.action.VIEW",
           "-d", url, "-p", BRAVE_PKG, "--activity-clear-top")
    time.sleep(random.uniform(9, 12))

    shot = os.path.join(shots, "results.png")
    if not screencap(adb, serial, shot):
        log(tag, "!! Ekran sekli alinmadi.")
        sys.exit(1)

    def bail(code, *msgs):
        """Xeta halinda: sekli tek bir yerde saxlayib (diaqnostika ucun) cixir."""
        for m in msgs:
            log(tag, m)
        if not keep:
            last = os.path.join(tempfile.gettempdir(), "bravebot-last.png")
            try:
                shutil.copy(shot, last)
                log(tag, f"   Son ekran sekli: {last}")
            except Exception:
                pass
            shutil.rmtree(shots, ignore_errors=True)
        sys.exit(code)

    cur = current_url(adb, serial)
    if "/sorry" in cur or "recaptcha" in cur.lower():
        bail(2, "!! Google bot yoxlamasi (CAPTCHA) cixdi -- dayanilir.",
             "   Bunu avtomatik kecmirik; brauzerin kukilerini temizlemek ve ya gozlemek lazimdir.")

    bands = find_link_bands(shot)
    if not bands:
        bail(1, "!! Netice linki tapilmadi.", f"   Unvan setri: {cur}")

    log(tag, f"{len(bands)} netice basligi tapildi (yuxaridan asagi).")
    n = max(1, min(args.result, len(bands)))
    ytop, ybot, xl, xr = bands[n - 1]
    tx = xl + (xr - xl) * random.uniform(0.25, 0.55)
    ty = ytop + (ybot - ytop) * random.uniform(0.35, 0.65)
    log(tag, f"-> {n}-ci neticeye toxunur ({int(tx)},{int(ty)})")

    before = cur
    human_tap(adb, serial, tx, ty)
    time.sleep(random.uniform(6, 9))

    after = current_url(adb, serial)
    if after == before:
        log(tag, "   (unvan deyismedi -- bir az gozlenilir)")
        time.sleep(4)
        after = current_url(adb, serial)

    log(tag, f"AÇILDI: {after}")
    if keep:
        screencap(adb, serial, os.path.join(shots, "opened.png"))

    touch_scroll(adb, serial, size, steps=random.randint(3, 6))
    time.sleep(args.stay)
    if keep:
        screencap(adb, serial, os.path.join(shots, "after_scroll.png"))
        log(tag, f"Ekran sekilleri: {shots}")
    else:
        shutil.rmtree(shots, ignore_errors=True)   # muveqqeti sekiller silinir
    log(tag, "Bitdi ✅")


if __name__ == "__main__":
    main()
