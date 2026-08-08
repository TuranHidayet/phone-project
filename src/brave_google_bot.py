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
    """
    Brave-in unvan setrini oxuyur.

    ONCE unvan setrinin OZ node-u (url_bar) axtarilir: bu Brave build-inde
    uiautomator veb mezmunu da gosterir, ona gore sadece "URL-e oxsayan ilk
    metn"i goturmek sehv idi -- sehifedeki netice unvanlari (mes. netice
    kartindaki "https://qebulol.az") unvan setri sanilir ve bot "sehv sehife
    acildi" deyib bosuna geri qayidirdi.
    """
    xml = ui_dump(adb, serial)
    for chunk in xml.split("<node")[1:]:
        if 'resource-id="com.brave.browser:id/url_bar"' in chunk:
            m = re.search(r'text="([^"]*)"', chunk)
            if m and m.group(1).strip():
                return m.group(1).strip()
            break

    cands = re.findall(r'text="([^"]{4,120})"', xml)
    # tam URL ve ya domen/yol
    for t in cands:
        if " " not in t and "/" in t and "." in t:
            return t
    # unvan setri cox vaxt yalniz domeni gosterir (mes. "kontakt.az");
    # sonluq herf olmalidir ki, "399.99" kimi qiymetler domen sanilmasin
    for t in cands:
        if " " not in t and re.match(r"^[\w-]+(\.[\w-]+)*\.[A-Za-z]{2,}$", t):
            return t
    # URL-e oxsar hec ne yoxdursa bos qaytar (bildiris metnini URL sanmayaq)
    return ""


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


def ui_dump(adb, serial):
    """
    UI agacini oxuyur. Dump ve cat BIR adb cagirisinda birlesdirilib --
    iki ayri cagiris her defe ~1 san elave vaxt aparirdi (skriptde onlarla dump var).
    """
    return adb_sh(adb, serial, "shell",
                  "uiautomator dump /sdcard/_ui.xml >/dev/null 2>&1; cat /sdcard/_ui.xml")


def node_center(xml, pattern):
    """Verilen naxisa uygun ilk node-un merkez koordinatini qaytarir."""
    for chunk in xml.split("<node")[1:]:
        if re.search(pattern, chunk):
            m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', chunk)
            if m:
                x1, y1, x2, y2 = map(int, m.groups())
                return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def open_url(adb, serial, pkg, url):
    """
    URL-i acir. application_id EXTRA-si sayesinde brauzer HER DEFE EYNI TABI
    tekrar istifade edir -- her isde yeni tab acilib yigilmir.
    """
    adb_sh(adb, serial, "shell", "am", "start", "-a", "android.intent.action.VIEW",
           "-d", url, "-p", pkg, "--activity-clear-top",
           "--es", "com.android.browser.application_id", pkg)


def close_bot_tab(adb, serial, pkg, tag):
    """
    Sonda botun tabini baglayir. Once sehife bosaldilir (about:blank) -- beleliklə
    tab basligi "New tab" olur ve BIZIM tab oldugu birmenali bilinir; istifadecinin
    oz tablarina toxunulmur.
    """
    open_url(adb, serial, pkg, "about:blank")
    time.sleep(2.5)

    # alt panel gizlidirse yuxari surusdurub uze cixart
    adb_sh(adb, serial, "shell", "input", "swipe", "360", "500", "360", "1100", "300")
    time.sleep(1.2)

    xml = ui_dump(adb, serial)
    sw = node_center(xml, r'resource-id="[^"]*tab_switcher_button"')
    if not sw:
        log(tag, "   (tab acari tapilmadi -- tab bos qaldi, yigilma olmayacaq)")
        return False
    human_tap(adb, serial, *sw)
    time.sleep(2.5)

    xml = ui_dump(adb, serial)
    # yalniz BOS ("New tab" / "about:blank") tabin baglama duymesi
    close_btn = node_center(xml, r'content-desc="Close (New tab|about:blank)[^"]*tab"')
    if not close_btn:
        log(tag, "   (bos tabin baglama duymesi tapilmadi -- tab bos qaldi)")
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        return False

    human_tap(adb, serial, *close_btn)
    time.sleep(1.5)
    log(tag, "   tab baglandi 🗙")
    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_HOME")
    return True


def _set_clear_checkboxes(adb, serial, xml):
    """
    "Delete browsing data" ekraninda YALNIZ tarixce+kuki+kes secili qalsin.
    Tabs / Saved passwords / Autofill / Site settings secilidirse cixarilir --
    istifadecinin oz melumatlari silinmesin.
    """
    want = {
        "Browsing history": True,
        "Cookies and site data": True,
        "Cached images and files": True,
        "Tabs": False,
        "Saved passwords": False,
        "Autofill form data": False,
        "Site settings": False,
    }
    last_title = None
    for chunk in xml.split("<node")[1:]:
        m = re.search(r'text="([^"]*)"', chunk)
        if 'resource-id="android:id/title"' in chunk and m:
            last_title = m.group(1)
        elif 'resource-id="android:id/checkbox"' in chunk and last_title in want:
            checked = 'checked="true"' in chunk
            if checked != want[last_title]:
                b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', chunk)
                if b:
                    x1, y1, x2, y2 = map(int, b.groups())
                    human_tap(adb, serial, (x1 + x2) // 2, (y1 + y2) // 2)
                    time.sleep(0.7)


def clear_browsing_data(adb, serial, tag):
    """
    Botun izlerini silir: Menyu -> History -> Delete browsing data ->
    All time -> Delete data. Yalniz tarixce, kuki ve kes gedir; istifadecinin
    tablari, parollari, autofill-i toxunulmur. Novbeti isde Google terefinden
    hec bir evvelki seans gorunmur.
    """
    log(tag, "Brauzer izleri temizlenir (tarixce+kuki+kes, All time)...")

    # alt panel gizlidirse uze cixart
    adb_sh(adb, serial, "shell", "input", "swipe", "360", "500", "360", "1100", "300")
    time.sleep(0.9)

    xml = ui_dump(adb, serial)
    menu = node_center(xml, r'resource-id="[^"]*id/menu_button"')
    if not menu:
        log(tag, "   (menyu duymesi tapilmadi -- temizlik atlanir)")
        return False
    human_tap(adb, serial, *menu)
    time.sleep(1.8)

    xml = ui_dump(adb, serial)
    hist = node_center(xml, r'text="(History|Tarix[^"]*)"')
    if not hist:
        log(tag, "   (History menyusu tapilmadi -- temizlik atlanir)")
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        return False
    human_tap(adb, serial, *hist)
    time.sleep(2.2)

    xml = ui_dump(adb, serial)
    btn = node_center(xml, r'resource-id="[^"]*clear_browsing_data_button"')
    if not btn:
        log(tag, "   (Delete browsing data duymesi tapilmadi -- temizlik atlanir)")
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        return False
    human_tap(adb, serial, *btn)
    time.sleep(2.2)

    xml = ui_dump(adb, serial)
    _set_clear_checkboxes(adb, serial, xml)

    # Time range -> All time (siyahida sonuncu variant)
    spinner = node_center(xml, r'resource-id="[^"]*id/spinner"')
    if spinner:
        human_tap(adb, serial, *spinner)
        time.sleep(1.1)
        xml2 = ui_dump(adb, serial)
        opts = []
        for chunk in xml2.split("<node")[1:]:
            if 'resource-id="android:id/text1"' in chunk:
                b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', chunk)
                if b:
                    x1, y1, x2, y2 = map(int, b.groups())
                    opts.append(((x1 + x2) // 2, (y1 + y2) // 2))
        if len(opts) >= 2:
            human_tap(adb, serial, *opts[-1])   # sonuncu = "All time"
            time.sleep(1.1)
        else:
            adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(1)

    # "Delete data" duymesi bezen ekran hele qurulmadigi ucun tapilmir --
    # bir nece defe yoxlanilir (metnle de: id deyisirse ehtiyat variant).
    clear_btn = None
    for _ in range(4):
        xml = ui_dump(adb, serial)
        clear_btn = (node_center(xml, r'resource-id="[^"]*id/clear_button"')
                     or node_center(xml, r'text="(Delete data|Məlumatları sil)"'))
        if clear_btn:
            break
        time.sleep(1.5)
    if not clear_btn:
        log(tag, "   (Delete data duymesi tapilmadi -- temizlik atlanir)")
        for _ in range(2):
            adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(1)
        return False
    human_tap(adb, serial, *clear_btn)
    time.sleep(2.8)

    # bezi hallarda tesdiq dialoqu cixir
    xml = ui_dump(adb, serial)
    conf = node_center(xml, r'resource-id="android:id/button1"')
    if conf:
        human_tap(adb, serial, *conf)
        time.sleep(1.4)

    # History sehifesinden tab-a geri qayit
    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(1.1)
    log(tag, "   izler temizlendi 🧹")
    return True


def main():
    p = argparse.ArgumentParser(description="Brave + Google axtaris botu (adb, chromedriver-siz)")
    p.add_argument("query", nargs="?", default="telefon", help="Axtaris sozu")
    p.add_argument("--result", type=int, default=1, help="Necenci netice acilsin (default 1)")
    p.add_argument("--udid", help="Cihaz serial / IP:port")
    p.add_argument("--stay", type=float, default=15, help="Acilan sehifede nece saniye qalsin")
    p.add_argument("--keep-tab", action="store_true",
                   help="Sonda tabi baglama (default: baglanir)")
    p.add_argument("--keep-data", action="store_true",
                   help="Sonda brauzer izlerini (tarixce/kuki/kes) silme (default: silinir)")
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
    open_url(adb, serial, BRAVE_PKG, url)
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

    if not args.keep_data:
        clear_browsing_data(adb, serial, tag)
    if not args.keep_tab:
        close_bot_tab(adb, serial, BRAVE_PKG, tag)
    log(tag, "Bitdi ✅")


if __name__ == "__main__":
    main()
