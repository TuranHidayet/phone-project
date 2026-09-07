#!/usr/bin/env python3
"""
Brave-in DEFAULT AXTARIS SISTEMINI Google edir (telefon basina bir defe).

NIYE LAZIMDIR: Brave-de default axtaris "Brave Search"-dur. Bot artiq
axtarisi INSAN KIMI -- unvan setrine yazib Enter basaraq -- edir; default
Google olmasa sorgu search.brave.com-a gedir ve is menasini itirir
(biz Google neticelerinde gorunmek isteyirik).

Istifade:
    source scripts/env.sh
    $PY scripts/set_google_search.py <serial>

Telefon acig olmalidir. Loop isleyirse evvelce dayandir:
    launchctl unload -w ~/Library/LaunchAgents/com.sanan.azstudy-loop.plist
"""

import re
import sys
import time

sys.path.insert(0, "/Users/a1234/phone-project/src")
from android_chrome_bot import find_adb, adb_sh
from brave_google_bot import ui_dump, node_center, human_tap

# Menyu/ayar setirleri telefonun DILINDEDIR -- taninan variantlar sadalanir.
SETTINGS_LABELS = ("Settings", "Parametrlər", "Ayarlar", "Настройки")
# QEYD: Brave-de setir CEM haldadir -- "Search engines". Tek hal ("Search engine")
# yazilanda tapilmirdi; ona gore her iki variant saxlanilir.
SEARCH_LABELS = ("Search engines", "Search engine",
                 "Axtarış sistemləri", "Axtarış sistemi",
                 "Arama motorları", "Поисковые системы")
# "Search engines" ekraninda birbasa muherrik siyahisi YOXDUR: evvelce
# hansi tab ucun teyin etdiyimizi secmek lazimdir. Bize adi tab lazimdir
# ("Standard Tab"), cunki bot gizli tabdan istifade etmir.
STANDARD_TAB_LABELS = ("Standard Tab", "Standart Tab", "Обычная вкладка")
GOOGLE_LABELS = ("Google",)


def tap_label(adb, serial, labels, what, tries=3):
    """Verilen adlardan birini tapib toxunur. Tapmasa asagi surusdurub axtarir."""
    for attempt in range(tries):
        xml = ui_dump(adb, serial)
        for lab in labels:
            pos = node_center(xml, r'text="%s"' % re.escape(lab))
            if pos:
                print(f"  {what}: '{lab}' tapildi {pos}")
                human_tap(adb, serial, *pos)
                time.sleep(2.0)
                return True
        # gorunmurse siyahini asagi surusdur
        adb_sh(adb, serial, "shell", "input", "swipe", "540", "1600", "540", "800", "350")
        time.sleep(1.2)
    print(f"  XETA: {what} tapilmadi ({labels})")
    return False


def main():
    serial = sys.argv[1] if len(sys.argv) > 1 else None
    if not serial:
        sys.exit("Istifade: set_google_search.py <serial>")
    adb = find_adb()

    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
    adb_sh(adb, serial, "shell", "wm", "dismiss-keyguard")
    time.sleep(1)

    xml = ui_dump(adb, serial)
    menu = node_center(xml, r'resource-id="[^"]*id/menu_button"')
    if not menu:
        sys.exit("XETA: menyu duymesi tapilmadi -- Brave on planda olmalidir")
    human_tap(adb, serial, *menu)
    time.sleep(2.0)

    if not tap_label(adb, serial, SETTINGS_LABELS, "Settings"):
        sys.exit(1)
    if not tap_label(adb, serial, SEARCH_LABELS, "Search engines"):
        sys.exit(1)
    if not tap_label(adb, serial, STANDARD_TAB_LABELS, "Standard Tab"):
        sys.exit(1)
    if not tap_label(adb, serial, GOOGLE_LABELS, "Google"):
        sys.exit(1)

    time.sleep(1.5)
    # Ayar ekranlarindan cix
    for _ in range(3):
        adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.2)

    print("\n=== YOXLAMA ===")
    xml = ui_dump(adb, serial)
    hint = ""
    for chunk in xml.split("<node")[1:]:
        m = re.search(r'text="([^"]*type URL[^"]*|[^"]*Search[^"]*)"', chunk)
        if m:
            hint = m.group(1)
            break
    print(f"unvan setrinin ipucu: {hint!r}")
    if "Brave" in hint:
        print("XEBERDARLIQ: hele Brave Search gorunur -- ayar tetbiq olunmayib")
    else:
        print("Google teyin edildi ✅")


if __name__ == "__main__":
    main()
