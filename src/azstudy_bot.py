#!/usr/bin/env python3
"""
AzStudy botu (REAL Android, chromedriver YOXDUR)
------------------------------------------------
Google-da "xaricde tehsil azstudy" axtarir -> neticelerde azstudy.az-i tapib
REAL barmaqla acir -> saytda verilen muddet qeder (default 90 san) gezir:
scroll edir, daxili sehifelere kecir -> sonda izleri silir, tabi baglayir.

AXIN (hamisi insan kimi, OS seviyyesinde real toxunusla):
  1) Brave acilir, UNVAN SETRINE sorgu YAZILIR ve Enter basilir.
     Sert: telefonun default axtarisi Google olmalidir (Brave-de default
     "Brave Search"-dur) -> bir defe: scripts/set_google_search.py <serial>
  2) Netice sehifesi SURUSDURULUR; her addimda UI agaci oxunur ve
     "https://azstudy.az" setri EKRANA DUSENDE ona toxunulur.
  3) Saytda gezilir; daxili sehifelere SEHIFEDEKI LINKE toxunmaqla kecilir
     (eyni tabda qalir + referrer yaranir). Link tutulmasa ehtiyat olaraq
     intent islenir.
  4) Sonda izler ve tablar bir gedisde temizlenir, ucus rejimi 3 saniye
     yandirilib sondurulur (mobil datada bu, public IP-ni firladir).

  KOHNE USUL (2026-09-07-de silindi): netice Brave-in "Find in page"
  funksiyasi ile taplirdi -- menyu, yazma, NARINCI isiqlanmanin ekran
  seklinden piksel-piksel axtarilmasi. Uc ayri asililigi vardi (menyu
  setrinin dili, tema rengi, ekran sekli sureti) ve her ucu problem cixardi.

  ELCATANLIQ AGACI HAQQINDA IKI TAPINTI (olculub 2026-09-07):
   1) Veb mezmunu `clickable="true"` ILE ISARELENMIR. Klikli gorunen node-lar
      ayri destedir (nav/konteyner) ve onlarin koordinatlari HEMISE ekrandan
      kenara yapisdirilmis qalir (y=2079) -- 25 surusdurmeden sonra da ekrana
      dusmurler. Meqale linkleri ise adi METN node-udur.
   2) Ona gore link axtaranda `clickable` YOXLANMIR: ekranda gorunen metn
      node-lari goturulur (onlar heqiqi koordinat verir), esl link olub-olmadigi
      ise TOXUNANDAN SONRA URL-in deyismesine gore yoxlanilir.
  Uzun muddet kod `clickable="true"` teleb edirdi ve mehz buna gore daxili
  kecidlerin yarisi itirdi.

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
    open_url, close_all_tabs, clear_browsing_data,
)
import stats
import notify

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

# Brave menyusundaki "Find in page" setri TELEFONUN DILINDE gorunur.
# Ilk uc telefon en-US oldugu ucun hermetik ingilis metni kifayet edirdi;
# Redmi 8 ise az-AZ-dir ve orada setir "Səhifədə tapın"-dir -- bot menyunu
# acirdi, amma setri tapa bilmeyib "Find in page acila bilmedi" verirdi.
# Menyu setirlerinin resource-id-si hamisinda eynidir (menu_item_text),
# ona gore id ile secmek olmur -- taninan variantlari sadalayiriq.
FIND_IN_PAGE_LABELS = (
    "Find in page",         # en
    "Səhifədə tapın",       # az
    "Найти на странице",    # ru
    "Sayfada bul",          # tr
)


def reveal_toolbar(adb, serial):
    """
    Menyu duymesini uze cixardir. Iki hal var:
      1) Sehifeni asagi surusdurende alt panel gizlenir -> kicik geri-surusdurme
      2) Brave TAB SIYAHISI ekraninda qalib (evvelki isden sonra) -> orada
         menyu yoxdur, ondan CIXMAQ lazimdir (BACK). Bu hal yoxlanmayanda bot
         "netice tapilmadi" xetasi verirdi.
    """
    for _ in range(4):
        xml = ui_dump(adb, serial)
        if "menu_button" in xml:
            return True
        if ("Search your tabs" in xml or "standard tabs" in xml
                or "tab_list_recycler_view" in xml):
            adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(1.6)
            continue
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


def read_find_status(xml):
    """Find panelindeki sayqac ("1/3", "0/0") -- yoxdursa bos setir."""
    for chunk in xml.split("<node")[1:]:
        if "find_status" in chunk:
            m = re.search(r'text="([^"]*)"', chunk)
            return m.group(1).strip() if m else ""
    return ""


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
    fip = None
    for label in FIND_IN_PAGE_LABELS:
        fip = node_center(xml, r'text="%s"' % re.escape(label))
        if fip:
            break
    if not fip:
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        return None
    human_tap(adb, serial, *fip)
    time.sleep(1.4)

    # QEYD: `input text` yalniz ASCII yaza bilir (ç, ə, ı isləmir) -- ona gore
    # axtarilan sozler ASCII olmalidir ("Daha", "azstudy.az").
    adb_sh(adb, serial, "shell", "input", "text", text.replace(" ", "%s"))

    # Netice sayi DERHAL hazir olmur. Evvel burada sabit `time.sleep(2.5)`
    # vardi: Google SERP agir sehifedir, yavas cihazda (Note 10S, Android 13)
    # Brave saymani hemin muddete bitirmirdi, status hele "0/0" oxunurdu.
    # Bot bundan "bu sehifede yoxdur" neticesi cixarib nahaq yere "daha cox
    # netice" duymesini axtarirdi ve "1-ci sehifede azstudy.az yoxdur" xetasi
    # verirdi -- halbuki sonradan ekranda "1/3" yazilirdi.
    # Indi sabit gozleme evezine status HAZIR OLANA QEDER gozlenilir.
    #
    # "0/0" DA duzgun cavab ola biler (mes. "Daha" duymesi hemin sehifede
    # yoxdursa) -- ona gore onu derhal qebul etmirik, amma 12 saniye de
    # gozlemirik: ust-uste IKI defe "0/0" oxunsa, sayma bitib demekdir.
    status = ""
    zeros = 0
    for _ in range(12):
        time.sleep(1.0)
        status = read_find_status(ui_dump(adb, serial))
        if status and status != "0/0":
            break
        zeros = zeros + 1 if status == "0/0" else 0
        if zeros >= 2:
            break

    hide_keyboard(adb, serial)      # yerlesim sabitlesir, isiqlanma qalir

    # Klaviatura baglananda sayma hele davam edirse, son deyeri goturek.
    return read_find_status(ui_dump(adb, serial)) or status


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
    # Hedler EKRAN OLCUSUNE nisbidir: telefonlar ferqli olcudedir
    # (720x1600 vs 1080x2340) -- sabit piksel qiymetleri boyuk ekranda
    # isiqlanmani/duymeni tapa bilmirdi.
    y_gap = max(20, int(h * 0.025))    # eyni zolagin setirleri arasi
    x_gap = max(15, int(w * 0.042))    # eyni obyektin pikselleri arasi
    min_w = max(25, int(w * 0.055))
    min_h = max(10, int(h * 0.009))
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
        if p[1] - cur[-1][1] <= y_gap:
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
            if p[0] - sub[-1][0] <= x_gap:
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
        if bw < min_w or bh < min_h:
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
    # Nisbi hedler (720x1600 etalonuna gore olculub)
    btn_h_min = int(h * 0.0375)        # ~60 px @1600
    btn_h_max = int(h * 0.094)         # ~150 px @1600
    row_gap = int(h * 0.0225)          # ~36 px @1600 (duymenin metn setri)
    edge = max(10, int(w * 0.014))     # ~10 px @720
    inset = max(25, int(w * 0.055))    # ~40 px @720
    footer_span = int(h * 0.26)        # ~420 px @1600

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
        if not (is_white(edge, y) and is_white(w - edge, y)):
            continue
        cnt = sum(1 for x in range(2 * edge, w - 2 * edge, 3) if is_gray(x, y))
        if cnt * 3 >= need:
            rows.append(y)
    if not rows:
        return None

    # Setirleri qruplasdir. Boslugu 36 piksel qeder "bagislayiriq": duymenin
    # ORTASINDAKI metn setri boz sayini asagi salir ve zolagi iki hisseye
    # bolurdu -- ona gore ardicilliq bir az yumsaq yoxlanilir.
    bands, cur = [], [rows[0]]
    for y in rows[1:]:
        if y - cur[-1] <= row_gap:
            cur.append(y)
        else:
            bands.append(cur)
            cur = [y]
    bands.append(cur)

    out = []
    for b in bands:
        if not (btn_h_min <= (b[-1] - b[0]) <= btn_h_max):
            continue
        # Duyme neredeyse tam eni tutur -> her iki kenari boz olmalidir.
        # Yoxlama zolagin TAM ORTASINDA aparilir: duyme tam yuvarlaqdir
        # (radius ~ hundurluyun yarisi), ona gore yuxarida/asagida kenarlar
        # hele agdir -- yalniz ortada en genis olur.
        y_test = (b[0] + b[-1]) // 2
        if is_gray(inset, y_test) and is_gray(w - inset, y_test):
            out.append(b)
    if not out:
        return None

    # Duyme HER ZAMAN sehifenin altbilgisinin (tam enli boz saha, #E8EAED)
    # hemen ustundedir. Bu sert orta sehifedeki boz kartlari kesir -- onlara
    # toxunanda botun sehv linke dusmesinin sebebi bu idi.
    def footer_below(band):
        for y in range(band[-1] + 10, min(h - 5, band[-1] + footer_span), 6):
            if (not is_white(edge, y)) and is_gray(edge, y) and is_gray(w - edge, y):
                return True
        return False

    withfooter = [b for b in out if footer_below(b)]
    b = (withfooter or out)[-1]               # en asagidaki = duyme
    return (w // 2, (b[0] + b[-1]) // 2)


def search_by_typing(adb, serial, tag, query):
    """
    Brave-i acir, UNVAN SETRINE toxunur, sorgunu YAZIR ve Enter basir.
    Qaytarir: Google neticeleri acildisa True.

    NIYE (2026-09-07): evvel hazir Google URL-i intentle acilirdi
    (`am start -d "google.com/search?q=..."`) -- yeni axtaris qutusu ile hec
    bir temas olmurdu. Bu, butun axinda insan davranisindan en cox ferqlenen
    addim idi: real istifadeci brauzeri acir, yazir, Enter basir.

    SERT: Brave-in default axtaris sistemi GOOGLE olmalidir. Brave-de default
    "Brave Search"-dur (olculub) -- o halda yazilan sorgu search.brave.com-a
    gedir ve is menasini itirir. Telefon qurulanda BIR DEFE:
        $PY scripts/set_google_search.py <serial>

    QEYD: `adb input text` yalniz ASCII yaza bilir (ç, ə, ı islemir);
    default sorgu ASCII-dir: "xaricde tehsil azstudy".
    """
    log(tag, f"Brave acilir, unvan setrine yazilir: '{query}'")
    adb_sh(adb, serial, "shell", "monkey", "-p", BRAVE_PKG,
           "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(random.uniform(4, 6))

    # Unvan setri: yuklenmis sehifede `url_bar`, yeni tab ekraninda
    # `search_box_text` olur -- ikisini de qebul edirik.
    bar = None
    for _ in range(4):
        xml = ui_dump(adb, serial)
        bar = node_center(xml, r'resource-id="[^"]*id/(url_bar|search_box_text)"')
        if bar:
            break
        time.sleep(1.5)
    if not bar:
        log(tag, "   (unvan setri tapilmadi)")
        return False

    human_tap(adb, serial, *bar)
    time.sleep(random.uniform(1.2, 2.0))
    adb_sh(adb, serial, "shell", "input", "text", query.replace(" ", "%s"))
    time.sleep(random.uniform(0.8, 1.6))
    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_ENTER")

    deadline = time.time() + 25
    while time.time() < deadline:
        time.sleep(2)
        u = current_url(adb, serial) or ""
        if "google." in u and "search" in u:
            return True
        if "search.brave.com" in u or "brave.com/search" in u:
            log(tag, "   XEBERDARLIQ: sorgu Brave Search-e getdi -- bu telefonda "
                     "default axtaris Google deyil "
                     "(bir defe: $PY scripts/set_google_search.py <serial>)")
            return False
    return False


def find_result_by_scroll(adb, serial, size, tag, max_scrolls=14):
    """
    Google neticelerinde azstudy.az-i SEHIFENI SURUSDUREREK tapir.
    Qaytarir: toxunulacaq (x, y) ve ya None.

    NIYE BELE (2026-09-07): evvel netice Brave-in "Find in page" funksiyasi ile
    taplirdi -- menyu acilir, "https://azstudy.az" yazilir, tapilan yer NARINCI
    isiqlanir, ekran sekli cekilib hemin narinci zolagin pikselleri axtarilirdi.
    Bu zencir uzun ve kovrek idi: menyu setri telefonun dilinden asili, isiqlanma
    rengi Google/Brave temasindan asili, ekran sekli ise yavas cihazda 40 saniye
    ceke bilir. Indi ise sadece SURUSDURUB UI AGACINDAN oxuyuruq.

    VACIB OLCU: Android ekrandan KENARDAKI veb node-larin heqiqi koordinatini
    vermir -- hamisini eyni serhed qiymetine "yapisdirir" (bu telefonda y=2079,
    ekran 2340). Ona gore "node-u tap, sonra ona teref surusdur" usulu ISLEMIR;
    node ekrana DUSENE qeder surusdurub y-nin heqiqi qiymet aldigini gozlemek
    lazimdir. Ust hedd 0.85h secilib ki, hemin serhed qiymeti kenarda qalsin.

    Netice olaraq URL setri ("https://azstudy.az") axtarilir: bu, saytin oz
    neticelerinde olur, Instagram/Facebook neticelerinde ise olmur -- ona gore
    sehv karta toxunmuruq.
    """
    w, h = size
    y_lo, y_hi = h * 0.15, h * 0.85

    for i in range(max_scrolls):
        xml = ui_dump(adb, serial)

        # Agac bos gelibse (sehife hele yuklenir) surusdurmek kome etmir.
        if xml.count("<node") == 0:
            time.sleep(1.8)
            continue

        for chunk in xml.split("<node")[1:]:
            m = re.search(r'text="([^"]*)"', chunk)
            if not m or SITE_MARK not in m.group(1):
                continue
            b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', chunk)
            if not b:
                continue
            x1, y1, x2, y2 = map(int, b.groups())
            cy = (y1 + y2) // 2
            if y_lo <= cy <= y_hi:
                log(tag, f"   netice {i + 1}-ci baxisda ekranda gorundu")
                return (x1 + x2) // 2, cy

        # Gorunmedi -- bir addim asagi. Insan kimi: orta suretli tek swipe.
        x = int(w * random.uniform(0.45, 0.55))
        adb_sh(adb, serial, "shell", "input", "swipe",
               str(x), str(int(h * 0.75)), str(x), str(int(h * 0.32)),
               str(random.randint(260, 460)))
        time.sleep(random.uniform(1.1, 2.0))

    return None


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


def wait_for_route(adb, serial, timeout=25):
    """
    Telefonda INTERNET MARSRUTU berpa olunana qeder gozleyir.

    `ip route get 8.8.8.8` cavabinda " dev <interfeys>" olanda sebeke hazirdir.
    Wi-Fi ucun bu wlan0, mobil data ucun ccmni0/rmnet olur -- ferqi yoxdur,
    yalniz marsrutun MOVCUDLUGU vacibdir.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            out = adb_sh(adb, serial, "shell", "ip route get 8.8.8.8")
            if " dev " in (out or ""):
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def airplane_cycle(adb, serial, tag, secs=3):
    """
    Isin sonunda ucus rejimini YANDIRIB-SONDURUR (sebeke qosulmasi sifirlanir).

    NIYE BELE YAZILIB (sade `adb shell` bes etmir):
      Telefon adb-ye Wi-Fi uzerinden qosuludur. Ucus rejimi Wi-Fi-i da sondurur,
      yeni EMRI GONDEREN ELAQE KESILIR -- "geri sondur" emri catmaz ve telefon
      ucus rejiminde ILISIB QALARDI. Ona gore butun ardicilliq TELEFONUN OZUNDE
      ayrilmis proses kimi (nohup ... &) islenir: elaqe kesilse de proses
      davam edir ve rejimi mutleq geri sondurur.

    Sonra Wi-Fi qayidana qeder gozlenilir ve adb elaqesi berpa edilir ki,
    novbeti dovr telefonu axtarmaq mecburiyyetinde qalmasin.
    """
    on_cmd = ("cmd connectivity airplane-mode enable || "
              "(settings put global airplane_mode_on 1; "
              "am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true)")
    off_cmd = ("cmd connectivity airplane-mode disable || "
               "(settings put global airplane_mode_on 0; "
               "am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false)")
    # sondurme ISTENILEN halda islensin deye ayrica ; ile yazilir (|| deyil)
    script = f"{on_cmd}; sleep {int(secs)}; {off_cmd}"

    log(tag, f"Ucus rejimi: {secs} san yandirilib sondurulur...")
    adb_sh(adb, serial, "shell", f"nohup sh -c '{script}' >/dev/null 2>&1 &")

    # Wi-Fi geri qalxana qeder gozle (adb elaqesi bu muddetde kesik olur).
    #
    # BUTUN CAGIRISLAR try/except ICINDEDIR: sebeke yoxdursa `adb connect`
    # cavabsiz qalib timeout atirdi ve bu istisna botu COKDURURDU (is ozu
    # ugurla bitmis olsa da dovr xeta ile qeyd olunurdu). Bu addim
    # "ela olsa yaxsi" xarakterlidir -- hec vaxt isi ucurmamalidir.
    # QEYD: ucus rejimindan sonra router telefona YENI IP verir (olculub:
    # 192.168.1.140 -> .151). Ona gore kohne unvana uzun-uzadi qosulmaga
    # calismaq menasizdir: qisa bir cehd edirik, alinmasa novbeti dovrde
    # find_phone.sh onu ~3 saniyede tapir.
    time.sleep(secs + 5)
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            subprocess.run([adb, "connect", serial],
                           capture_output=True, text=True, timeout=8)
            state = subprocess.run([adb, "-s", serial, "get-state"],
                                   capture_output=True, text=True,
                                   timeout=8).stdout.strip()
            if state == "device":
                # adb elaqesi var -- amma bu, INTERNETIN qayitdigi demek DEYIL.
                # Telefon USB-de olanda (mobil data rejimi) ucus rejimi adb-ye
                # umumiyyetle toxunmur: "device" cavabi derhal gelir ve bot
                # sebekenin qayitdigini ZENN EDIRDI. Mobil datada ise LTE-ye
                # yeniden qosulma bir nece saniye cekir, novbeti is sebekesiz
                # baslaya bilerdi. Ona gore DEFAULT MARSRUT yoxlanilir.
                if wait_for_route(adb, serial):
                    log(tag, "   sebeke qayitdi ✅")
                    return True
                log(tag, "   (adb var, amma internet marsrutu qayitmadi)")
                return False
        except Exception:
            pass                          # timeout / adb xetasi -- normaldir
        time.sleep(3)
    log(tag, "   (IP deyisib -- novbeti dovrde telefon yeniden tapilacaq)")
    return False


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


def click_internal_link(adb, serial, size, tag):
    """
    Sehifede gorunen DAXILI linklerden birine TESADUFI secib REAL TOXUNUSLA kecir.

    NIYE INTENT DEYIL (2026-09-07): evvel daxili sehifeler `am start` intenti ile
    acilirdi. Iki problemi vardi:
      1) Brave her intenti YENI TAB-da acir -- bir isde 4 tab yigilirdi.
         (open_url-daki `application_id` extra-si kohne AOSP Browser davranisidir;
          muasir Chromium onu etibarli saymir.)
      2) Intentle acilan sehifenin REFERRER-i olmur -- saytda 3 ayri "birbasa
         giris" kimi gorunur, halbuki bir seansda daxili klikler gorunmelidir.
    Linke toxunanda hem EYNI TABDA qalir, hem de referrer zenciri yaranir.

    QEYD: bu Brave build-i veb mezmununu uiautomator agacinda gosterir
    (olculub: sehifede 13 klik oluna bilen link) -- faylin basindaki kohne
    "veb mezmunu gorunmur" qeydi bu versiyaya aid deyil.

    Qaytarir: kecid alindisa True.
    """
    w, h = size
    y_lo, y_hi = h * 0.15, h * 0.88       # ekranin "toxunula bilen" zolagi

    # BASLANGIC UNVANI ETIBARLI OXUNMALIDIR. Sehifeni asagi surusdurende
    # unvan paneli gizlenir ve current_url BOS qaytarir. Bos "before" ile
    # "sehife deyismedi" yoxlamasi ISLEMIR: bot mətnə toxunub hec yere
    # kecmediyi halda bunu UGUR sayirdi (olculub -- log-da eyni URL iki defe
    # "daxili sehife" kimi yazilmisdi). Ona gore panel uze cixarilir.
    before = ""
    for _ in range(3):
        before = current_url(adb, serial) or ""
        if before:
            break
        adb_sh(adb, serial, "shell", "input", "swipe",
               str(w // 2), str(int(h * 0.35)), str(w // 2), str(int(h * 0.60)), "300")
        time.sleep(1.2)

    # Linke OXSAMAYAN gorunen metnler (altliqda olurlar) -- bosuna toxunmayaq.
    not_link = re.compile(
        r"@|VÖEN|\+994|^\d|WhatsApp$|^Menu$|^Axtar$|Back to top", re.IGNORECASE)

    def find_links(xml, min_len=20):
        """
        EKRANDA gorunen, linke oxsayan metn node-lari: [(metn, x, y), ...].

        VACIB TAPINTI (olculub 2026-09-07): bu Brave build-inde veb mezmunu
        `clickable="true"` ILE ISARELENMIR. Klikli gorunen node-lar tamamile
        AYRI destedir (nav/konteyner) ve onlarin koordinatlari her zaman
        ekrandan kenara "yapisdirilmis" qalir -- 25 surusdurmeden sonra da
        ekrana dusmurler. Kod ise mehz `clickable="true"` teleb edirdi, yeni
        DUZGUN node-lari ozu kenarlasdirirdi; daxili kecidlerin yarisinin
        itmesinin esl sebebi bu idi.

        Meqale linkleri (oxsar yazilar bolmesi) adi METN node-udur ve ekrana
        dusende HEQIQI koordinat verir -- olculub:
            klik=False (559,542) "Polşada Bakalavr Təhsili Almaq – ..."
        Ona gore burada `clickable` yoxlanilmir. Metnin esl link olub-olmadigi
        TOXUNANDAN SONRA URL-e gore yoxlanilir (uc namized sinanilir).
        """
        out = []
        for chunk in xml.split("<node")[1:]:
            t = re.search(r'text="([^"]+)"', chunk)
            b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', chunk)
            if not t or not b:
                continue
            txt = t.group(1).strip()
            # UST HEDD: link basliqlari teqriben 30-90 herfdir, meqale
            # ABZASLARI ise 100+ olur. Ust hedd olmayanda bot abzasa toxunurdu
            # (olculub: "Avropa ilə Yaxın Şərqi birləşdirən Türkiyə, güclü
            # mədən..." -- link deyil, metndir).
            if not (min_len <= len(txt) <= 95) or not_link.search(txt):
                continue
            x1, y1, x2, y2 = map(int, b.groups())
            out.append((txt, (x1 + x2) // 2, (y1 + y2) // 2))
        return out

    def swipe(down=True):
        """
        Istiqametli swipe. touch_scroll insan kimi gezinti ucundur --
        istiqameti qarisiq olur, mueyyen yere catmaq ucun yaramir.

        SURETLI VE UZUN: meqale linkleri (oxsar yazilar) sehifenin ALTINDADIR;
        olculub ki, yumsaq surusdurmelerle 8 addimda ora catmaq olmur, sert
        surusdurme ile ise ~25 addima catilir. Ona gore yol uzun (0.80->0.20),
        muddet qisadir.
        """
        x = int(w * random.uniform(0.45, 0.55))
        y1, y2 = (int(h * 0.80), int(h * 0.20)) if down else (int(h * 0.20), int(h * 0.80))
        adb_sh(adb, serial, "shell", "input", "swipe", str(x), str(y1), str(x), str(y2),
               str(random.randint(180, 260)))
        time.sleep(random.uniform(0.5, 0.9))

    # 1) LINKLERI TAP. Agac bos gelerse (uiautomator sehife yuklenerken bezen
    #    "idle" halina catmir) surusdurmek kome etmir -- gozleyib tekrar oxuyuruq.
    links = []
    for attempt in range(4):
        xml = ui_dump(adb, serial)
        if xml.count("<node") == 0:
            time.sleep(2.0)
            continue
        links = find_links(xml)
        if links:
            break
        swipe(down=True)

    if not links:
        log(tag, "   (sehifede uygun link tapilmadi)")
        return False

    # 2) EKRANDA GORUNEN link tapilana qeder SURUSDUR.
    #
    #    NIYE BELE: Android ekrandan KENARDAKI veb node-larin heqiqi
    #    koordinatini vermir -- hamisini eyni serhed qiymetine yapisdirir
    #    (bu telefonda y=2079). Ona gore "hedefi sec, sonra ona teref
    #    surusdur" usulu prinsipce ISLEMIR (sinandi, geri qaytarildi).
    #    Isleyen yeganne yol: link EKRANA DUSENE qeder surusdurmek --
    #    find_result_by_scroll-da eyni usul isleyir.
    #
    #    Evvel cemi 2 defe surusdurulurdu ve kecidlerin YARISI itirdi
    #    (olculub). Meqale sehifesi uzundur: oxsar yazilar, kateqoriya
    #    linkleri ve altliq asagidadir -- oraya catmaq ucun daha cox
    #    surusdurme lazimdir. Bu, hem de real oxucu davranisidir.
    #    HEDD MERHELELIDIR. Evvel her zaman 25+ herf teleb olunurdu ve 10
    #    surusdurmeden sonra da "ekranda link yoxdur" cixirdi -- halbuki
    #    ekranda linkler VAR idi: sehifenin altina catmisdiq, oradaki altliq
    #    ve kateqoriya linkleri ise QISADIR ("Haqqımızda", "Əlaqə") ve uzun
    #    heddle ozumuz onlari kenarlasdirirdiq.
    #    Indi evvel meqale basliqlari axtarilir, tapilmasa hedd asagi dusur.
    #    CEHD SAYI QESDEN AZDIR (3). Daha cox surusdurme SINANDI ve geri
    #    qaytarildi: 6 ve 10 cehd ikinci kecidi xilas etmedi (sebeb asagida),
    #    amma isi 330 saniyelik limite catdirib gozetciye oldurtdu.
    #    Yuxari surusdurme de sinandi -- netice deyismedi.
    #
    #    SEBEB (olculub): Brave-in elcatanliq agaci ekrandan KENARDAKI veb
    #    elementlerin heqiqi koordinatini vermir, hamisini y=2079-a yapisdirir.
    #    Ona gore linki "gorub ona teref getmek" MUMKUN DEYIL -- yalniz
    #    tesaduf ekrana dusenler tutulur. Bu, kodun deyil, platformanin
    #    mehdudiyyetidir; daha cox cehd yalniz vaxt yeyir.
    visible = [l for l in links if y_lo <= l[2] <= y_hi]
    for i in range(8):
        if visible:
            break
        swipe(down=True)
        xml = ui_dump(adb, serial)
        if xml.count("<node") == 0:
            time.sleep(1.5)
            continue
        links = find_links(xml, 20)
        visible = [l for l in links if y_lo <= l[2] <= y_hi]

    if not visible:
        log(tag, f"   (8 surusdurmeden sonra da ekranda link yoxdur; "
                 f"agacda {len(links)} link var)")
        return False

    # 3) NAMIZEDLERI BIR-BIR SINA.
    #    Evvel bir namized secilirdi ve alinmasa derhal el cekilirdi. Amma
    #    `clickable="true"` olan HER node esl link deyil -- karusel/konteyner
    #    ola biler (olculub: "URL deyismedi ... link deyilmis"). Real oxucu da
    #    bele halda basqa linke kecir, ona gore uc namizede qeder sinanilir.
    tried = set()
    for _ in range(3):
        cands = [l for l in visible if l[0] not in tried]
        if not cands:
            break
        target, x, y = random.choice(cands)
        tried.add(target)

        log(tag, f"-> linke toxunulur: {target[:55]}")
        human_tap(adb, serial, x, y)

        # KECIDI GOZLE. Evvel sabit 5-8 saniye gozlenilirdi; mobil datada agir
        # sehife bu muddete acilmirdi, URL kohne qalirdi ve bot "link deyilmis"
        # qerari verirdi. Indi URL DEYISENE qeder gozlenilir.
        time.sleep(3)
        deadline = time.time() + 15
        while time.time() < deadline:
            cur = current_url(adb, serial) or ""
            if cur and cur != before:
                break
            time.sleep(2)

        dismiss_popups(adb, serial, tag)

        # UNVANI OXU. Panel gizli ola biler (sehifeni asagi surusdurende
        # yigilir), o halda current_url BOS qaytarir. Bos deyer "namelum"dur,
        # "kenar sayt" DEYIL -- evvel bele basa dusulurdu ve bot nahaq yere
        # geri qayidib butun kecidleri pozurdu.
        after = ""
        for _ in range(3):
            after = current_url(adb, serial) or ""
            if after:
                break
            adb_sh(adb, serial, "shell", "input", "swipe",
                   str(w // 2), str(int(h * 0.35)), str(w // 2), str(int(h * 0.60)), "300")
            time.sleep(1.4)

        if after and SITE_HOST not in after:
            log(tag, f"   (kenar sehife: {after} -- geri qayidilir)")
            adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(random.uniform(3, 5))
        elif after and before and after == before:
            log(tag, "   (URL deyismedi -- link deyilmis, basqasi sinanilir)")
        else:
            log(tag, f"   daxili sehife: {after or '(unvan oxunmadi)'}")
            return True

        # Ugursuz cehdden sonra ekran deyismis ola biler -- namizedleri
        # yeniden oxuyuruq.
        xml = ui_dump(adb, serial)
        if xml.count("<node"):
            visible = [l for l in find_links(xml, 10) if y_lo <= l[2] <= y_hi]

    return False


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
            # ESAS YOL: sehifedeki tesadufi daxili linke real toxunus --
            # eyni tabda qalir ve referrer yaranir.
            if not click_internal_link(adb, serial, size, tag):
                # EHTIYAT: gorunen hissede uygun link yoxdursa (mes. sehife
                # sonunda serh bolmesindeyik) kohne usulla -- intentle -- keciriк.
                # Bu halda yeni tab acilir, amma gezinti dayanmir.
                nxt = pages[page_i]
                log(tag, f"-> (link tapilmadi) intentle: {nxt}")
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
    p.add_argument("--airplane", type=int, default=3, metavar="SAN",
                   help="Isin sonunda ucus rejimini bu qeder saniye yandirib "
                        "sondur (0 = etme, default 3)")
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
    t_start = time.time()

    def bail(code, *msgs):
        for m in msgs:
            log(tag, m)
        # Xeta qeyde alinir ve Telegram-a bildiris gedir (qurasdirilibsa).
        # Bildiris gonderilmese de bot normal sekilde dayanir.
        err = msgs[0].lstrip("! ").strip() if msgs else "namelum xeta"
        stats.record(serial, prof["model"], prof["android"], args.query,
                     "error", time.time() - t_start, error=err,
                     name=prof.get("name"), hw=prof.get("hw"))
        notify.send(f"❌ <b>{prof.get('name') or prof['model']}</b>\n"
                    f"Bot xəta ilə dayandı:\n{err}")
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

    # Hazir URL yalniz EHTIYAT ucun saxlanilir: esas yol sorgunu unvan setrine
    # YAZMAQDIR (insan kimi). Yazmaq alinmasa is dayanmasin deye kohne usula
    # kecirik -- ve bunu loga yaziriq ki, ne qeder tez-tez oldugu gorunsun.
    url = f"https://www.google.com/search?q={quote_plus(args.query)}"
    if not search_by_typing(adb, serial, tag, args.query):
        log(tag, "   (yazmaqla axtaris alinmadi -- hazir URL ile davam edilir)")
        open_url(adb, serial, BRAVE_PKG, url)
        time.sleep(random.uniform(9, 12))

    cur = current_url(adb, serial)
    if "/sorry" in cur or "recaptcha" in cur.lower():
        bail(2, "!! Google bot yoxlamasi (CAPTCHA) cixdi -- dayanilir.")

    # --- azstudy.az-i neticelerde tap: sehife-sehife, "Daha cox netice" basaraq
    after = ""
    found = False
    for page in range(1, MAX_PAGES + 1):
        pos = find_result_by_scroll(adb, serial, size, tag)

        # BERPA: netice tapilmadisa evvelce Brave-in hele SERP-de olduguna
        # baxiriq. Brave on plandan dusubse (ana ekran, ilisib qalmis dialoq)
        # agac oxunmur ve netice "yoxdur" kimi gorunur -- bu, sehifede
        # heqiqeten olmamasindan FERQLI haldir.
        for attempt in (1, 2):
            if pos is not None:
                break
            u = current_url(adb, serial) or ""
            if "google" in u:
                break                     # SERP-dedik, sadece bu sehifede yoxdur
            log(tag, f"   Brave itdi -- SERP-e qaytarilir (cehd {attempt}/2)...")
            adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
            adb_sh(adb, serial, "shell", "wm", "dismiss-keyguard")
            open_url(adb, serial, BRAVE_PKG, url)
            time.sleep(random.uniform(8, 11))
            pos = find_result_by_scroll(adb, serial, size, tag)

        if pos is not None:
            log(tag, f"'{SITE_MARK}' {page}-ci sehifede tapildi (scroll ile).")
            # URL setrinin OZUNE toxunuruq: mobil Google-da netice blokunun
            # URL setri de klikleniendir. Altdaki basliq ziyaret edilibse
            # rengi deyisir, ona gore etibarli olan URL setridir.
            log(tag, f"-> neticeye toxunulur ({pos[0]},{pos[1]})")
            human_tap(adb, serial, *pos)
            time.sleep(random.uniform(6, 9))
            dismiss_popups(adb, serial, tag)

            # Unvani sayt acilana qeder gozle. Sabit gozleme mobil datada
            # catmirdi; ustelik BOS unvan "sehv sehife" saylirdi -- halbuki
            # bos deyer sadece "unvan setri oxunmadi" demekdir (panel gizli
            # ola biler). Bu, nahaq yere SERP-e qayitmaga sebeb olurdu.
            after = ""
            deadline = time.time() + 15
            while time.time() < deadline:
                after = current_url(adb, serial) or ""
                if SITE_HOST in after:
                    break
                time.sleep(2)
            if SITE_HOST in after:
                found = True
                break
            log(tag, f"   sehv sehife acildi ({after or 'unvan oxunmadi'}) -- SERP-e qayidilir")
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

    # Tablar TEMIZLIKLE EYNI ANDA baglanir ("Delete browsing data" ekranindaki
    # "Tabs" qutusu) -- evvel bunun ucun ayrica UI gedisi vardi (tab siyahisi ->
    # menyu -> hamisini bagla), yeni her isde elave dump-lar ve elave vaxt.
    cleared = False
    if not args.keep_data:
        cleared = clear_browsing_data(adb, serial, tag, close_tabs=not args.keep_tab)

    # EHTIYAT: temizlik bas tutmasa (menyu tapilmadi ve s.) tablar da
    # baglanmamis qalir ve yigilmaga baslayir -- bu hal olculdu. Ona gore
    # yalniz HEMIN halda ayrica tab gedisi edilir.
    if not args.keep_tab and not cleared:
        close_all_tabs(adb, serial, BRAVE_PKG, tag)

    secs = time.time() - t_start
    stats.record(serial, prof["model"], prof["android"], args.query,
                 "ok", secs, url=after, name=prof.get("name"), hw=prof.get("hw"))
    # Her ugurlu is ucun bildiris SUSMAYA gore gonderilmir (gunde ~280 mesaj
    # olardi); yalniz NOTIFY_EACH_RUN=1 verilibse gonderilir. Xetalar ve
    # gunluk hesabat her halda gedir.
    if os.environ.get("NOTIFY_EACH_RUN") == "1":
        notify.send(f"✅ <b>{prof.get('name') or prof['model']}</b>\n"
                    f"{after or 'azstudy.az'} — {secs:.0f} san", silent=True)
    log(tag, f"Bitdi ✅ ({secs:.0f} san)")

    # EN SONDA: ucus rejimi yandirilib-sondurulur (sebeke sifirlanir).
    # Qeyd artiq yazilib -- elaqe kesilse bele statistika itmir.
    if args.airplane > 0:
        airplane_cycle(adb, serial, tag, args.airplane)


if __name__ == "__main__":
    main()
