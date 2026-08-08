#!/usr/bin/env python3
"""
AzStudy botu (REAL Android, chromedriver YOXDUR)
------------------------------------------------
Google-da "xaricde tehsil azstudy" axtarir -> neticelerde azstudy.az-i tapib
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
    $PY src/azstudy_bot.py --stay 120 --query "xaricde tehsil azstudy"
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

# Neticelerde axtarilan soz. "azstudy" YOX, "azstudy.az" -- cunki qisa variant
# video karuselindeki "AzStudy" kanal etiketine de dusur ve toxunus sehv karta gedir.
SITE_MARK = "https://azstudy.az"   # Instagram neticesindeki "azstudy.az" adi ile qarismasin
SITE_HOST = "azstudy.az"

# Google mobil SERP-in sonundaki "daha cox netice" duymesinin metni
# QEYD: `adb input text` ASCII-den kenar herfleri (ç, ə, ı) yaza bilmir,
# ona gore duymenin yalniz ASCII hissesi axtarilir: "Daha çox axtarış" -> "Daha"
MORE_BTN_TEXT = "Daha"
MAX_PAGES = 5                              # necenci sehifeye qeder baxsin

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


def reveal_toolbar(adb, serial):
    """
    Sehifeni asagi surusdurende Brave-in alt paneli gizlenir (menyu duymesi
    itir). Kicik geri-surusdurme ile paneli uze cixardiriq.
    """
    for _ in range(3):
        if "menu_button" in ui_dump(adb, serial):
            return True
        adb_sh(adb, serial, "shell", "input", "swipe", "360", "600", "360", "900", "300")
        time.sleep(1.1)
    return "menu_button" in ui_dump(adb, serial)


def keyboard_shown(adb, serial):
    """Ekran klaviaturasi aciqdirmi (BACK-in neyi baglayacagini bilmek ucun)."""
    out = adb_sh(adb, serial, "shell", "dumpsys", "input_method")
    m = re.search(r"mInputShown=(true|false)", out)
    return bool(m) and m.group(1) == "true"


def hide_keyboard(adb, serial):
    """
    Klaviaturani baglayir (aciqdirsa). Klaviatura aciq ikene sehife sixilir --
    ekran seklindeki koordinat toxunus aninda sursur ve sehv linke dusur.
    Isiqlanma klaviatura baglananda YERINDE QALIR (olculub).
    """
    if keyboard_shown(adb, serial):
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.4)
        return True
    return False


def close_find_bar(adb, serial):
    """Find panelini baglayir (aciqdirsa)."""
    for _ in range(3):
        if "find_toolbar" not in ui_dump(adb, serial):
            return
        hide_keyboard(adb, serial)
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.1)


def find_prev(adb, serial):
    """
    Find panelinde "evvelki" duymesi. 1-ci uygunluqdan basilanda SONUNCUYA
    kecir -- "Daha cox netice" duymesi sehifenin en altinda oldugu ucun bu,
    ona catmagin en qisa yoludur.
    """
    xml = ui_dump(adb, serial)
    prev = node_center(xml, r'resource-id="[^"]*find_prev_button"')
    if not prev:
        return False
    human_tap(adb, serial, *prev)
    time.sleep(1.8)
    return True


def find_in_page(adb, serial, tag, text):
    """
    Menyu -> Find in page -> metni yazir -> KLAVIATURANI BAGLAYIR.
    Klaviatura acilanda sehife sixilir ve isiqlanmanin yeri surusur; baglayandan
    sonra yerlesim sabit qalir, isiqlanma ise qalir.
    Qaytarir: find_status ("1/3", "0/0") ve ya None (panel acilmadi).
    """
    if not reveal_toolbar(adb, serial):
        return None

    xml = ui_dump(adb, serial)
    menu = node_center(xml, r'resource-id="[^"]*id/menu_button"')
    if not menu:
        return None
    human_tap(adb, serial, *menu)
    time.sleep(1.8)

    xml = ui_dump(adb, serial)
    fip = node_center(xml, r'text="Find in page"')
    if not fip:
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        return None
    human_tap(adb, serial, *fip)
    time.sleep(1.4)

    # QEYD: `input text` yalniz ASCII yaza bilir (ç, ə, ı isləmir) -- ona gore
    # axtarilan sozler ASCII olmalidir ("Daha", "azstudy.az").
    adb_sh(adb, serial, "shell", "input", "text", text.replace(" ", "%s"))
    time.sleep(2.5)

    hide_keyboard(adb, serial)      # yerlesim sabitlesir, isiqlanma qalir

    xml = ui_dump(adb, serial)
    status = ""
    for chunk in xml.split("<node")[1:]:
        if "find_status" in chunk:
            m = re.search(r'text="([^"]*)"', chunk)
            if m:
                status = m.group(1).strip()
            break
    return status


def find_highlight(png_path, size):
    """
    Ekran seklinde narinci Find-in-page isiqlanmasini tapir.
    Sag kenar (scrollbar isareleri) ve yuxari find paneli istisna edilir.
    Bir nece narinci zona olarsa EN BOYUYU secilir (aktiv uygunluq odur).
    Qaytarir: (x, y) merkez ve ya None.
    """
    from PIL import Image
    im = Image.open(png_path).convert("RGB")
    w, h = im.size
    px = im.load()
    x_max = int(w * 0.85)              # scrollbar isareleri sag kenardadir
    y_min = int(h * 0.20)              # find paneli / unvan setri istisna
    hits = []
    for y in range(y_min, h - 100, 2):
        for x in range(8, x_max, 2):
            r, g, b = px[x, y]
            if r > HL_MIN_R and HL_G_LO < g < HL_G_HI and b < HL_MAX_B:
                hits.append((x, y))
    if len(hits) < 30:
        return None

    # Evvelce y-e gore zolaqlara, sonra HER ZOLAGI x-e gore ayri-ayri
    # obyektlere boluruk. Yalniz y-e gore qruplasdiranda eyni setirdeki
    # baska narinci obyekt (mes. sayt loqosu) isiqlanma ile birlesir ve
    # sixliq suni sekilde asagi dusurdu.
    hits.sort(key=lambda p: p[1])
    ybands, cur = [], [hits[0]]
    for p in hits[1:]:
        if p[1] - cur[-1][1] <= 40:
            cur.append(p)
        else:
            ybands.append(cur)
            cur = [p]
    ybands.append(cur)

    clusters = []
    for band in ybands:
        band.sort(key=lambda p: p[0])
        sub = [band[0]]
        for p in band[1:]:
            if p[0] - sub[-1][0] <= 30:
                sub.append(p)
            else:
                clusters.append(sub)
                sub = [p]
        clusters.append(sub)

    # Find-in-page isiqlanmasi DOLU dorbucaqdir; sehifedeki narinci METN
    # (mes. xerite kartinda "Tezlikle baglanacaq") nazik strixlerden ibaretdir.
    # Ona gore klasterin oz cercevesi icinde ne qeder "dolu" oldugu yoxlanilir.
    def solid(cl):
        xs = [p[0] for p in cl]
        ys = [p[1] for p in cl]
        bw = max(xs) - min(xs) + 2
        bh = max(ys) - min(ys) + 2
        if bw < 40 or bh < 14:
            return 0.0
        return len(cl) / max(1.0, (bw / 2) * (bh / 2))

    good = [c for c in clusters if len(c) >= 30 and solid(c) >= 0.45]
    if not good:
        return None
    best = max(good, key=len)
    xs = [p[0] for p in best]
    ys = [p[1] for p in best]
    return (sum(xs) // len(xs), sum(ys) // len(ys))


def find_more_button(png_path):
    """
    Sehifenin altindaki "Daha çox axtarış nəticəsi" duymesini FORMASINA gore
    tapir: ag fon uzerinde acig-boz (241,243,244) genis yuvarlaq zolaq.
    Metnle axtarmaqdan (Find in page) daha etibarlidir -- "daha" sozu snippet
    icinde de ola bilir ve toxunus sehv linke dusurdu.
    Qaytarir: (x, y) ve ya None.
    """
    from PIL import Image
    im = Image.open(png_path).convert("RGB")
    w, h = im.size
    px = im.load()
    # Astana 45% -- duymenin metn setrinde (ustelik Find-in-page isiqlanmasi
    # varsa daha da) boz piksel sayi azalir.
    need = int(w * 0.45)

    def is_gray(x, y):
        """
        Duymenin fonu (241,243,244). Find paneli aciqdirsa sagdaki surusdurme
        zolagi hemin sahenin bir hissesini biraz agardir (251,252,252) -- ona
        gore diapazon genisdir; sert 'tam ag' ayri yoxlanilir.
        """
        r, g, b = px[x, y]
        return 232 <= r <= 253 and 234 <= g <= 254 and 235 <= b <= 254

    def is_white(x, y):
        r, g, b = px[x, y]
        return r >= 254 and g >= 254 and b >= 254

    rows = []
    for y in range(int(h * 0.25), h - 60, 3):
        # duymenin SOL/SAG kenarinda ag bosluq var; tam enli boz bolme (mes.
        # "Bunlari da axtarirlar" fonu, altbilgi) bu sertde kesilir
        if not (is_white(10, y) and is_white(w - 10, y)):
            continue
        cnt = sum(1 for x in range(20, w - 20, 3) if is_gray(x, y))
        if cnt * 3 >= need:
            rows.append(y)
    if not rows:
        return None

    # Setirleri qruplasdir. Boslugu 36 piksel qeder "bagislayiriq": duymenin
    # ORTASINDAKI metn setri boz sayini asagi salir ve zolagi iki hisseye
    # bolurdu -- ona gore ardicilliq bir az yumsaq yoxlanilir.
    bands, cur = [], [rows[0]]
    for y in rows[1:]:
        if y - cur[-1] <= 36:
            cur.append(y)
        else:
            bands.append(cur)
            cur = [y]
    bands.append(cur)

    out = []
    for b in bands:
        if not (60 <= (b[-1] - b[0]) <= 150):
            continue
        # Duyme neredeyse tam eni tutur -> her iki kenari boz olmalidir.
        # Yoxlama zolagin TAM ORTASINDA aparilir: duyme tam yuvarlaqdir
        # (radius ~ hundurluyun yarisi), ona gore yuxarida/asagida kenarlar
        # hele agdir -- yalniz ortada en genis olur.
        y_test = (b[0] + b[-1]) // 2
        if is_gray(40, y_test) and is_gray(w - 40, y_test):
            out.append(b)
    if not out:
        return None

    # Duyme HER ZAMAN sehifenin altbilgisinin (tam enli boz saha, #E8EAED)
    # hemen ustundedir. Bu sert orta sehifedeki boz kartlari kesir -- onlara
    # toxunanda botun sehv linke dusmesinin sebebi bu idi.
    def footer_below(band):
        for y in range(band[-1] + 10, min(h - 5, band[-1] + 420), 6):
            if (not is_white(10, y)) and is_gray(10, y) and is_gray(w - 10, y):
                return True
        return False

    withfooter = [b for b in out if footer_below(b)]
    b = (withfooter or out)[-1]               # en asagidaki = duyme
    return (w // 2, (b[0] + b[-1]) // 2)


def goto_more_button(adb, serial, tag, shot):
    """
    "Daha cox netice" duymesine catir ve onun DEQIQ yerini qaytarir.

    Iki usul birlesdirilib:
      1) Surusdurme Find in page ile edilir ("Daha" axtarilir, sonra "evvelki"
         ile SONUNCU uygunluga kecilir -- o da sehifenin altindaki duymedir).
         Elle swipe etmek sekil karuselinde ilisib qalir ve sehv yere toxunur.
      2) Toxunus koordinati isiqlanmadan DEYIL, duymenin formasindan alinir
         (ag fonda genis acig-boz zolaq) -- beleliklə qonsu linke dusmuruk.
    Qaytarir: (x, y) / None (duyme yoxdursa = son sehife).
    """
    status = find_in_page(adb, serial, tag, MORE_BTN_TEXT)
    if status is None or status in ("", "0/0"):
        return None
    find_prev(adb, serial)          # 1-ci uygunluqdan sonuncuya = sehifenin alti
    time.sleep(1.2)

    for _ in range(3):
        if screencap(adb, serial, shot):
            btn = find_more_button(shot)
            if btn:
                return btn
        time.sleep(1.2)
    return None


def find_result_link(png_path, near_y):
    """
    Isiqlanmis URL setrinin (mes. "https://azstudy.az") ALTINDAKI mavi netice
    basligini tapir -- Google mobil yerlesiminde toxunulasi link odur.
    Mavi basliq zolaqlari brave_google_bot-un olculmus detektoru ile tapilir.
    """
    from brave_google_bot import find_link_bands
    bands = find_link_bands(png_path, skip_top_frac=0.12)
    below = [b for b in bands if b[0] >= near_y - 10]
    if not below:
        return None
    ytop, ybot, xl, xr = min(below, key=lambda b: b[0])
    if ytop - near_y > 260:                  # cox uzaqdirsa bizim netice deyil
        return None
    return (xl + (xr - xl) * random.uniform(0.25, 0.55),
            ytop + (ybot - ytop) * random.uniform(0.35, 0.65))


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
        time.sleep(1.0)
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
    p.add_argument("--query", default="xaricde tehsil azstudy",
                   help="Google axtaris sozu (default: brend sozu ile -- sayt 1-ci sehifede olur)")
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

    # --- azstudy.az-i neticelerde tap: sehife-sehife, "Daha cox netice" basaraq
    after = ""
    found = False
    for page in range(1, MAX_PAGES + 1):
        close_find_bar(adb, serial)
        status = find_in_page(adb, serial, tag, SITE_MARK)
        if status is None:
            bail(1, "!! Find in page acila bilmedi.")

        if status not in ("", "0/0"):
            log(tag, f"'{SITE_MARK}' {page}-ci sehifede tapildi (status: {status}).")
            hl = stable_highlight(adb, serial, size, shot, tag)
            if not hl:
                bail(1, "!! Narinci isiqlanma ekranda tapilmadi.")
            # Isiqlanmanin OZUNE toxunuruq: mobil Google-da netice blokunun
            # URL setri de klikleniendir. Altdaki "mavi basliq"i axtarmaq sehv
            # idi -- ziyaret edilmis linkler benovseyi olur, detektor onlari
            # gormur ve asagidaki yad neticeni secirdi.
            log(tag, f"-> neticeye toxunulur ({int(hl[0])},{int(hl[1])})")
            human_tap(adb, serial, *hl)
            time.sleep(random.uniform(6, 9))
            dismiss_popups(adb, serial, tag)

            after = current_url(adb, serial)
            if SITE_HOST not in after:
                time.sleep(4)
                after = current_url(adb, serial)
            if SITE_HOST in after:
                found = True
                break
            log(tag, f"   sehv sehife acildi ({after or '?'}) -- SERP-e qayidilir")
            adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(random.uniform(5, 7))
            continue

        # bu sehifede yoxdur -> sona qeder scroll edib "Daha cox netice"ni bas
        log(tag, f"   {page}-ci sehifede yoxdur, daha cox netice yuklenir...")
        close_find_bar(adb, serial)
        btn = goto_more_button(adb, serial, tag, shot)
        if not btn:
            bail(1, f"!! {page}-ci sehifede azstudy.az yoxdur ve 'daha cox netice' "
                    f"duymesi tapilmadi (son sehife ola biler).")
        log(tag, f"   'daha cox netice' duymesine toxunulur ({btn[0]},{btn[1]})")
        human_tap(adb, serial, *btn)
        time.sleep(random.uniform(6, 8))

        # toxunus sehven bir linke dusubse (SERP-den cixmisiqsa) geri qayit
        u = current_url(adb, serial)
        if u and "google" not in u:
            log(tag, f"   (toxunus linke dusdu: {u} -- geri qayidilir)")
            adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(random.uniform(5, 7))

    if not found:
        bail(1, f"!! azstudy.az ilk {MAX_PAGES} sehifede tapilmadi.")

    log(tag, f"AÇILDI: {after or '(unvan oxunmadi)'}")

    browse_site(adb, serial, size, tag, args.stay)

    shutil.rmtree(shots, ignore_errors=True)

    if not args.keep_data:
        clear_browsing_data(adb, serial, tag)
    if not args.keep_tab:
        close_bot_tab(adb, serial, BRAVE_PKG, tag)
    log(tag, "Bitdi ✅")


if __name__ == "__main__":
    main()
