#!/usr/bin/env python3
"""
Təkmilləşdirilmiş dövr botu:
  1. Google-da "xeberler" axtar -> 5-10 saniyə yuxarı-aşağı scroll
  2. Geri -> "idman xeberleri" axtar -> 5-10 saniyə scroll
  3. Geri -> "web developer turanly" axtar -> turanly.com-u tapıb kliklə
  4. turanly.com-da İLK olaraq yuxarı-aşağı scroll -> sonra 1-2 dəqiqə gəzmək
     (axtarış nəticələrindən linkləri tapıb klikləmək)
  5. Bitəndə YALNIZ tabları bağlamaq, tarixçə/kuki silməmək

Əsasən android_chrome_bot köməkçilərindən istifadə edir.
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import tempfile
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from android_chrome_bot import (
    find_adb, adb_sh, detect_devices, device_profile, touch_scroll,
    log,
)
from brave_google_bot import (
    BRAVE_PKG, ui_dump, node_center, human_tap,
    find_link_bands, current_url, open_url,
    clear_browsing_data, close_all_tabs, screencap,
)

BOT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_screen(adb, serial):
    import re as _re
    sz = adb_sh(adb, serial, "shell", "wm", "size")
    dn = adb_sh(adb, serial, "shell", "wm", "density")
    mo = _re.search(r"Override size:\s*(\d+)x(\d+)", sz)
    if mo:
        size = f"{mo.group(1)}x{mo.group(2)}"
    else:
        mp = _re.search(r"Physical size:\s*(\d+)x(\d+)", sz)
        size = f"{mp.group(1)}x{mp.group(2)}" if mp else "?"
    mdo = _re.search(r"Override density:\s*(\d+)", dn)
    if mdo:
        density = int(mdo.group(1))
    else:
        md = _re.search(r"(\d+)", dn)
        density = int(md.group(1)) if md else 0
    return size, density


def apply_screen(adb, serial, size, density):
    adb_sh(adb, serial, "shell", "wm", "size", size)
    adb_sh(adb, serial, "shell", "wm", "density", str(density))
    time.sleep(1.8)


def reset_screen(adb, serial):
    adb_sh(adb, serial, "shell", "wm", "size", "reset")
    adb_sh(adb, serial, "shell", "wm", "density", "reset")
    time.sleep(1.0)


def go_google_home(adb, serial):
    open_url(adb, serial, BRAVE_PKG, "https://www.google.com")
    time.sleep(random.uniform(4, 5.5))


def type_query(adb, serial, size, query):
    q = ui_dump(adb, serial)
    bar = node_center(q, r'resource-id="com\.brave\.browser:id/url_bar"')
    if bar is None:
        bar = (size[0] // 2, 177)
    human_tap(adb, serial, bar[0], bar[1])
    time.sleep(random.uniform(0.7, 1.0))
    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_CTRL_A")
    time.sleep(random.uniform(0.25, 0.4))
    for ch in query:
        adb_sh(adb, serial, "shell", "input", "text",
               "%s" if ch == " " else ch)
        time.sleep(random.uniform(0.06, 0.16))
    adb_sh(adb, serial, "shell", "input", "keyevent", "66")
    time.sleep(random.uniform(4.5, 6))


def browse_results(adb, serial, size, seconds=8):
    end = time.time() + seconds + random.uniform(0, 2)
    steps = 0
    while time.time() < end:
        if random.random() < 0.7:
            touch_scroll(adb, serial, size, steps=random.randint(2, 4))
        else:
            # yuxarı scroll üçün swipe-i tərs edirik
            w, h = size
            x = int(w * random.uniform(0.40, 0.60))
            y1 = int(h * random.uniform(0.25, 0.40))
            y2 = int(h * random.uniform(0.70, 0.80))
            adb_sh(adb, serial, "shell", "input", "swipe",
                   str(x), str(y1), str(x), str(y2), str(random.randint(220, 550)))
        time.sleep(random.uniform(1.2, 2.0))
        steps += 1
        if steps > 12:
            break


def find_and_click_turanly(adb, serial, shot_path):
    for _ in range(5):
        if not screencap(adb, serial, shot_path):
            break
        bands = find_link_bands(shot_path)
        if not bands:
            touch_scroll(adb, serial, (1080, 2340), steps=random.randint(3, 4))
            time.sleep(1.8)
            continue
        for b in bands:
            ytop, ybot, xl, xr = b
            tx = xl + (xr - xl) * 0.4
            ty = ytop + (ybot - ytop) * 0.5
            # toxunma öncəsi - koordinatları yoxlamaq üçün ekran çəkirik
            human_tap(adb, serial, tx, ty)
            time.sleep(random.uniform(5, 7))
            cur = current_url(adb, serial)
            if "turanly" in cur.lower():
                return True, cur
            # səhvə klikləndik, geri qayıt
            adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(random.uniform(2, 3))
            break
        else:
            continue
        break
    return False, current_url(adb, serial)


def browse_site(adb, serial, size, minutes=1.5):
    """turanly.com-da gəzmək: əvvəl scroll, sonra daxili linklərə klik"""
    end = time.time() + minutes * 60 + random.uniform(10, 25)
    clicks = 0
    # ilk olaraq yuxarı-aşağı scroll
    for _ in range(random.randint(4, 6)):
        touch_scroll(adb, serial, size, steps=random.randint(3, 5))
        time.sleep(random.uniform(1.0, 1.8))
    time.sleep(random.uniform(2, 4))
    while time.time() < end and clicks < 6:
        # ara sıra scroll
        for _ in range(random.randint(2, 4)):
            if random.random() < 0.8:
                touch_scroll(adb, serial, size, steps=random.randint(2, 4))
            else:
                w, h = size
                x = int(w * random.uniform(0.40, 0.60))
                y1 = int(h * random.uniform(0.25, 0.40))
                y2 = int(h * random.uniform(0.70, 0.80))
                adb_sh(adb, serial, "shell", "input", "swipe",
                       str(x), str(y1), str(x), str(y2), str(random.randint(220, 550)))
            time.sleep(random.uniform(0.8, 1.4))
        # bəzən linkə klik etməyə cəhd et (screenshot + band)
        if random.random() < 0.35 and clicks < 4:
            shot = os.path.join(tempfile.gettempdir(), f"_site_{int(time.time())}.png")
            if screencap(adb, serial, shot):
                bands = find_link_bands(shot)
                if bands:
                    b = random.choice(bands)
                    ytop, ybot, xl, xr = b
                    human_tap(adb, serial, xl + (xr - xl)*0.35,
                              ytop + (ybot - ytop)*0.5)
                    clicks += 1
                    time.sleep(random.uniform(4, 7))
                    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
                    time.sleep(random.uniform(2, 3))
            try:
                os.unlink(shot)
            except:
                pass
        time.sleep(random.uniform(2, 4))


SCREEN_PRESETS = {
    "a05-small":  ("720x1600",  320, "Samsung Galaxy A05",  "budget"),
    "redmi-c":    ("720x1600",  264, "Xiaomi Redmi 12C",    "budget"),
    "se-compact": ("750x1334",  326, "iPhone SE 3 (kiçik)", "mid"),
    "a54-mid":    ("1080x2340", 420, "Samsung Galaxy A54",  "mid"),
    "pixel-7":    ("1080x2400", 420, "Google Pixel 7",      "flagship"),
    "native":     ("1080x2340", 440, "Redmi Note 9 (real)", "native"),
}
DEFAULT_ORDER = ["a05-small", "redmi-c", "se-compact",
                 "a54-mid", "pixel-7", "native"]


def run_cycle(adb, serial, size, shots_dir, tag):
    """Tək dövrü icra et"""
    result = {"ok": True, "steps": []}

    # 1. xeberler
    log(tag, "   [1/4] Google -> 'xeberler'")
    go_google_home(adb, serial)
    type_query(adb, serial, size, "xeberler")
    browse_results(adb, serial, size, seconds=random.randint(5, 9))
    result["steps"].append("xeberler")
    time.sleep(1)
    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(random.uniform(2, 3))

    # 2. idman xeberleri
    log(tag, "   [2/4] Google -> 'idman xeberleri'")
    go_google_home(adb, serial)
    type_query(adb, serial, size, "idman xeberleri")
    browse_results(adb, serial, size, seconds=random.randint(5, 9))
    result["steps"].append("idman xeberleri")
    time.sleep(1)
    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(random.uniform(2, 3))

    # 3. web developer turanly -> klik
    log(tag, "   [3/4] Google -> 'web developer turanly' -> turanly.com")
    go_google_home(adb, serial)
    type_query(adb, serial, size, "web developer turanly")
    time.sleep(random.uniform(4, 5.5))
    shot = os.path.join(shots_dir, f"search_{int(time.time())}.png")
    clicked, url = find_and_click_turanly(adb, serial, shot)
    try:
        if os.path.exists(shot):
            os.unlink(shot)
    except:
        pass
    result["clicked_turanly"] = clicked
    result["url"] = url
    log(tag, f"      {url} (turanly click: {clicked})")

    # 4. saytda gəzmək
    if clicked or "turanly" in url.lower():
        log(tag, "   [4/4] turanly.com-da gəzmək (1-1.8 dəq)")
        browse_site(adb, serial, size, minutes=1.4)
        result["browsed_site"] = True
    else:
        log(tag, "      !! turanly tapılmadı / kliklənmədi")
        result["browsed_site"] = False

    return result


def main():
    p = argparse.ArgumentParser(description="Təkmilləşdirilmiş dövr botu")
    p.add_argument("--query-base", default="xeberler", help="ilk axtarış")
    p.add_argument("--result", type=int, default=1)
    p.add_argument("--stay", type=float, default=0)
    p.add_argument("--devices", default=",".join(DEFAULT_ORDER))
    p.add_argument("--udid", default=None)
    p.add_argument("--list", action="store_true")
    p.add_argument("--out", default=None)
    p.add_argument("--rounds", type=int, default=2)
    args = p.parse_args()

    if args.list:
        for k, (sz, dn, ad, tier) in SCREEN_PRESETS.items():
            print(f"  {k:14s} {sz:11s} @{dn:4d}dpi  [{tier:8s}] {ad}")
        return

    names = [n.strip() for n in args.devices.split(",") if n.strip()]
    bad = [n for n in names if n not in SCREEN_PRESETS]
    if bad:
        print(f"!! Naməlum preset: {', '.join(bad)}. --list ilə bax.")
        sys.exit(1)

    adb = find_adb()
    if not adb:
        print("!! adb tapılmadı")
        sys.exit(1)
    import subprocess as _sp
    out = _sp.run([adb, "devices"], capture_output=True, text=True).stdout
    ready = [l.split()[0] for l in out.splitlines()[1:]
             if len(l.split()) == 2 and l.split()[1] == "device"]
    serial = args.udid or (ready[0] if ready else None)
    if not serial:
        print("!! Cihaz tapılmadı")
        sys.exit(1)

    model = adb_sh(adb, serial, "shell", "getprop", "ro.product.model") or serial
    tag = model
    orig_size, orig_density = get_screen(adb, serial)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out or os.path.join("reports", "cycle2", stamp)
    os.makedirs(out_dir, exist_ok=True)

    log(tag, f"İyileşdirilmiş dövr: {len(names)} ekran ölçüsü | {args.rounds} dövr")
    log(tag, f"Öncəki ekran: {orig_size} @ {orig_density}dpi")
    log(tag, f"Çıxış: {out_dir}")

    all_results = []
    try:
        for r in range(args.rounds):
            log(tag, f"\n{'='*60}")
            log(tag, f"  DÖVR #{r+1}/{args.rounds}")
            log(tag, f"{'='*60}")
            for i, name in enumerate(names, 1):
                sz, dn, ad, tier = SCREEN_PRESETS[name]
                log(tag, f"\n━━━ [D{r+1}.{i}] {ad} ━━━ {sz} @{dn}dpi [{tier}]")
                apply_screen(adb, serial, sz, dn)
                sz2, dn2 = get_screen(adb, serial)
                log(tag, f"   tətbiq olundu: {sz2} @ {dn2}dpi")
                shots_dir = os.path.join(out_dir, f"r{r+1}", name)
                os.makedirs(shots_dir, exist_ok=True)
                try:
                    res = run_cycle(adb, serial, (1080, 2340), shots_dir, tag)
                    res.update({"round": r+1, "preset": name, "device": ad,
                                "tier": tier, "wm_size": sz, "wm_density": dn})
                    all_results.append(res)
                except Exception as e:
                    log(tag, f"   XƏTA: {e}")
                    all_results.append({"round": r+1, "preset": name, "device": ad,
                                        "ok": False, "error": str(e)})
                reset_screen(adb, serial)
                time.sleep(2)
    finally:
        reset_screen(adb, serial)
        sz, dn = get_screen(adb, serial)
        log(tag, f"\nEkran bərpa olundu: {sz} @ {dn}dpi")

    rep = os.path.join(out_dir, "report.json")
    with open(rep, "w") as f:
        json.dump({"query_flow": ["xeberler", "idman xeberleri",
                                  "web developer turanly"],
                   "device": model, "udid": serial,
                   "rounds": args.rounds, "when": stamp,
                   "results": all_results}, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  İYİLƏŞDİRİLMİŞ DÖVR TAMAMLANDI")
    ok = sum(1 for x in all_results if x.get("ok", True) and
             x.get("clicked_turanly"))
    print(f"  Dövr: {len(all_results)} | turanly-a klik: {ok}")
    print(f"  Hesabat: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    main()
