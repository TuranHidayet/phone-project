#!/usr/bin/env python3
"""
Turanli saytini telefonda FARKLI EKRAN OLCULERINDE test edir.

Android-in `wm size` / `wm density` override-i real ekrani veji deyisdirir --
yeni muxtelif cihaz olculerini (iPhone, Galaxy, iPad, desktop) simulyasiya
edirik, sayti acir, skrinshot aliriq ve her olcude:
  * sayt acildimi (URL yoxlanisi)
  * YATAY OVERFLOW varmi (sola surushdurub evvelki ekranla ferq yoxlanir)
  * ekrandan xarica cixan element varmi (uiautomator bounds)

SONDA her shey `wm size reset` / `wm density reset` ile GERI qaytarilir.

Istifade:
  $PY src/responsive_test.py                      # default turanly.com
  $PY src/responsive_test.py https://turanly.com/en --devices iphone_se,ipad
  $PY src/responsive_test.py --list               # olculeri goster
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from android_chrome_bot import (  # noqa: E402
    adb_sh, detect_devices, find_adb, log,
)

BRAVE_PKG = "com.brave.browser"

# isim -> (dp_en, dp_boy, density/dpi)
# Not: wm override pikseli = dp * density / 160  hesablanir.
PRESETS = {
    "iphone_se":     (375, 667, 320),
    "iphone_14":     (390, 844, 460),
    "iphone_14_pm":  (430, 932, 460),
    "galaxy_s21":    (360, 800, 420),
    "pixel_7":       (412, 915, 420),
    "redmi_note9":   (393, 873, 440),   # cihazin oz ORIGINAL olcusu (baseline)
    "small_android": (320, 640, 240),
    "ipad":          (768, 1024, 160),
    "ipad_pro":      (834, 1194, 160),
    "desktop_1366":  (1366, 768, 160),
    "desktop_1920":  (1920, 1080, 160),
}

DEFAULT_DEVICES = [
    "small_android", "iphone_se", "iphone_14", "iphone_14_pm",
    "galaxy_s21", "pixel_7", "redmi_note9", "ipad", "ipad_pro",
    "desktop_1366", "desktop_1920",
]

# dp'den hesablamaga gerek olmayan, dəqiq piksel override (baseline comparison)
EXACT_PX = {"redmi_note9": (1080, 2340)}


def wm(adb, serial, *args):
    return adb_sh(adb, serial, "shell", "wm", *args).strip()


def apply_preset(adb, serial, name, dp_w, dp_h, density):
    if name in EXACT_PX:
        px_w, px_h = EXACT_PX[name]
    else:
        px_w = max(320, round(dp_w * density / 160))
        px_h = max(480, round(dp_h * density / 160))
    wm(adb, serial, "size", f"{px_w}x{px_h}")
    wm(adb, serial, "density", str(density))
    time.sleep(1.6)
    return px_w, px_h


def reset_display(adb, serial, tag):
    wm(adb, serial, "size", "reset")
    wm(adb, serial, "density", "reset")
    time.sleep(1.6)
    log(tag, "   ekran olcusu GERI qaytarildi (wm size/density reset)")


def screencap(adb, serial, out_path):
    with open(out_path, "wb") as f:
        p = subprocess.run([adb, "-s", serial, "exec-out", "screencap", "-p"],
                           stdout=f, stderr=subprocess.DEVNULL)
    return p.returncode == 0 and os.path.getsize(out_path) > 1000


def open_url(adb, serial, url, wait=4.0):
    adb_sh(adb, serial, "shell", "am", "start", "-a",
           "android.intent.action.VIEW", "-d", url, "-p", BRAVE_PKG,
           "--activity-clear-top", "--es",
           "com.android.browser.application_id", BRAVE_PKG)
    time.sleep(random.uniform(wait, wait + 1.5))


def ui_dump(adb, serial, path="/sdcard/_rt.xml"):
    return adb_sh(adb, serial, "shell",
                  f"uiautomator dump {path} >/dev/null 2>&1; cat {path}")


def current_url(adb, serial):
    xml = ui_dump(adb, serial)
    for chunk in xml.split("<node")[1:]:
        if 'resource-id="com.brave.browser:id/url_bar"' in chunk:
            m = re.search(r'text="([^"]*)"', chunk)
            if m and m.group(1).strip():
                return m.group(1).strip()
    return ""


def diff_ratio(a_path, b_path, skip_top=0.16, skip_bot=0.10):
    """Iki ekran sekli arasindaki ferq nisbeti (0..1)."""
    from PIL import Image
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    w, h = a.size
    y0, y1 = int(h * skip_top), int(h * (1 - skip_bot))
    pa, pb = a.load(), b.load()
    total = changed = 0
    for y in range(y0, y1, 3):
        for x in range(4, w - 4, 3):
            total += 1
            ra, ga, ba = pa[x, y]
            rb, gb, bb = pb[x, y]
            if abs(ra - rb) + abs(ga - gb) + abs(ba - bb) > 48:
                changed += 1
    return changed / max(1, total)


def horizontal_overflow(adb, serial, shots_dir, name):
    """
    Sagdan sola surushdururuk: sehife genisdirse (overflow / carousels)
    ekran deyisir, deyilmezse eyni qalir.
    -> (varmi_siqnal, deyisim_nisbeti)
    """
    before = os.path.join(shots_dir, f"{name}_a.png")
    after = os.path.join(shots_dir, f"{name}_b.png")
    if not screencap(adb, serial, before):
        return None, 0.0

    h = _screen_h(adb, serial)
    y = int(h * 0.55)
    # Keneden baslamiriq (geri jesti) -- ortadan sola surushdururuk
    adb_sh(adb, serial, "shell", "input", "swipe",
           str(int(_screen_w(adb, serial) * 0.75)), str(y),
           str(int(_screen_w(adb, serial) * 0.22)), str(y), "520")
    time.sleep(1.8)
    screencap(adb, serial, after)

    ratio = diff_ratio(before, after)
    # geri qaytaraq ki sonraki testler deyer
    adb_sh(adb, serial, "shell", "input", "swipe",
           str(int(_screen_w(adb, serial) * 0.22)), str(y),
           str(int(_screen_w(adb, serial) * 0.75)), str(y), "520")
    time.sleep(1.2)
    return ratio > 0.03, ratio


def overflowing_nodes(adb, serial):
    """Ekrан xaricinda qalan (x2 > en) clickable elementleri sayir."""
    xml = ui_dump(adb, serial, "/sdcard/_rt2.xml")
    w = _screen_w(adb, serial)
    n = 0
    for chunk in xml.split("<node")[1:]:
        m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', chunk)
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        if x2 > w + 8 and (x2 - x1) > 40 and y2 > y1:
            n += 1
    return n


_screen_cache = {}


def _wm_size(adb, serial):
    """
    Aktual ekrani pikselde qaytarir.

    QEYD: `wm size` iki setir qaytarir:
        Physical size: 1080x2340
        Override size: 750x1334
    Override OLMAZDIR, ancaq real ekrani OVERRIDE eden deyere gore movzudur --
    yoxsa koordinatlar (swipe / bounds yoxlanisi) eski 1080x2340-a gore
    hesablanir ve kicik ekranlarda swipe ekrandan xarica cixir.
    """
    s = adb_sh(adb, serial, "shell", "wm", "size")
    m = re.search(r"Override size: (\d+)x(\d+)", s)
    if not m:
        m = re.search(r"Physical size: (\d+)x(\d+)", s)
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 2340)


def _screen_w(adb, serial):
    key = (serial, "w")
    if key not in _screen_cache:
        _screen_cache[key] = _wm_size(adb, serial)[0]
    return _screen_cache[key]


def _screen_h(adb, serial):
    key = (serial, "h")
    if key not in _screen_cache:
        _screen_cache[key] = _wm_size(adb, serial)[1]
    return _screen_cache[key]


def clear_cache():
    _screen_cache.clear()


def looks_loaded(url, target):
    """URL yuklenib-yuklenmediyini (consent/xxx sorusu deyil) yoxlayir."""
    if not url:
        return False
    u = url.lower()
    if "/sorry" in u or "recaptcha" in u:
        return False
    return True


def main():
    p = argparse.ArgumentParser(description="Sayti muxtelif ekran olculerinde test")
    p.add_argument("url", nargs="?", default="https://turanly.com",
                   help="Test olunacaq URL")
    p.add_argument("--udid", default=None, help="Cihaz seriali")
    p.add_argument("--devices", default=",".join(DEFAULT_DEVICES),
                   help="Vergul ile preset adlari (--list ile goster)")
    p.add_argument("--out", default=None, help="Cixis qovlugu")
    p.add_argument("--list", action="store_true", help="Presetleri goster ve cix")
    p.add_argument("--skip-reset", action="store_true",
                   help="SONDA ekran olcusunu geri qaytarma")
    args = p.parse_args()

    if args.list:
        for k, (w, h, d) in PRESETS.items():
            px = EXACT_PX.get(k, (round(w * d / 160), round(h * d / 160)))
            print(f"  {k:16s} {w}x{h} dp @ {d}dpi -> {px[0]}x{px[1]} px override")
        return

    adb = find_adb()
    ready, problems = detect_devices(adb)
    if not ready:
        print("!! Hech bir cihaz tapilmadi (adb devices).")
        if problems:
            print("   " + ", ".join(f"{s}={st}" for s, st in problems))
        sys.exit(1)
    serial = args.udid or ready[0]
    model = serial
    try:
        model = adb_sh(adb, serial, "shell", "getprop", "ro.product.model") or serial
    except Exception:
        pass
    tag = model

    names = [n.strip() for n in args.devices.split(",") if n.strip()]
    bad = [n for n in names if n not in PRESETS]
    if bad:
        print(f"!! Namayum preset: {', '.join(bad)}. --list ile bax.")
        sys.exit(1)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", args.url.lower()).strip("-")[:40]
    out = args.out or os.path.join("reports", "responsive", f"{slug}-{stamp}")
    os.makedirs(out, exist_ok=True)

    log(tag, f"Responsive test: {args.url}")
    log(tag, f"Presets: {', '.join(names)}")
    log(tag, f"Cixis: {out}")

    results = []
    try:
        for name in names:
            dp_w, dp_h, density = PRESETS[name]
            px_w, px_h = apply_preset(adb, serial, name, dp_w, dp_h, density)
            clear_cache()

            open_url(adb, serial, args.url, wait=5.0)
            time.sleep(1.5)

            url = current_url(adb, serial)
            loaded = looks_loaded(url, args.url)

            shot = os.path.join(out, f"{name}.png")
            got = screencap(adb, serial, shot)

            ov_signal = None
            ov_ratio = 0.0
            out_nodes = 0
            if got:
                ov_signal, ov_ratio = horizontal_overflow(
                    adb, serial, out, name)
                out_nodes = overflowing_nodes(adb, serial)

            status = "OK" if (loaded and got) else "PROBLEM"
            log(tag, f"{status:8s} {name:16s} "
                     f"{dp_w}x{dp_h}@{density} -> {px_w}x{px_h}px | "
                     f"overflow_sign={ov_signal} ({ov_ratio:.3f}) | "
                     f"out_nodes={out_nodes}")
            if not loaded:
                log(tag, f"         URL: {url[:90]}")

            results.append({
                "preset": name, "dp": [dp_w, dp_h], "density": density,
                "override_px": [px_w, px_h], "loaded": loaded,
                "url": url, "screenshot": os.path.abspath(shot) if got else None,
                "horizontal_scroll_signal": ov_signal,
                "horizontal_scroll_diff": round(ov_ratio, 4),
                "nodes_outside_viewport": out_nodes,
                "status": status,
            })
    finally:
        if not args.skip_reset:
            reset_display(adb, serial, tag)
        clear_cache()

    rep = os.path.join(out, "report.json")
    with open(rep, "w") as f:
        json.dump({"url": args.url, "device": model, "udid": serial,
                   "when": stamp, "results": results}, f, indent=2)

    # Xulasa
    print("\n=== XULASA ===")
    probs = [r for r in results if r["status"] != "OK"]
    ovf = [r for r in results if r["horizontal_scroll_signal"]]
    oob = [r for r in results if r["nodes_outside_viewport"] > 0]
    print(f"  test olunan olcu: {len(results)}   "
          f"problemi olan: {len(probs)}")
    if probs:
        print("  YUKLENME PROBLEMI:")
        for r in probs:
            print(f"    - {r['preset']} ({r['status']})")
    if ovf:
        print("  YATAY SCROLL / OVERFLOW SIGNALI (tovsiye: layout-u yoxla):")
        for r in ovf:
            print(f"    - {r['preset']}: diff={r['horizontal_scroll_diff']}")
    if oob:
        print("  EKRAN XARICI ELEMENTLER:")
        for r in oob:
            print(f"    - {r['preset']}: {r['nodes_outside_viewport']} dene")
    if not probs and not ovf and not oob:
        print("  Her shey yaxshidi -- hec bir overflow tapilmadi.")
    print(f"  Skrinshotlar: {os.path.abspath(out)}")
    print(f"  Report: {os.path.abspath(rep)}")


if __name__ == "__main__":
    main()
