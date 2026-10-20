#!/usr/bin/env python3
"""
Botun tam dövrünü (Google -> yaz -> klik -> gəz -> təmizlə) fərqli
ekran ölçülərində ardicil işə salır.

Hər dövr:
  1. wm size + wm density tətbiq olunur (real ekran çözünürlüyü dəyişir)
  2. brave_google_bot.py subprocess olaraq işə düşür
  3. Nəticə toplanır (screenshot + status)
  4. Ekran bərpa olunur → növbəti preset

Bu, CDP viewport-dan fərqli olaraq TELEFONUN EKRANINI HƏQİQƏTƏN dəyişir.

İstifade:
  $PY src/cycle_runner.py
  $PY src/cycle_runner.py --url https://turanly.com --query "turanly"
  $PY src/cycle_runner.py --devices a05-small,se-compact,native
  $PY src/cycle_runner.py --list
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from android_chrome_bot import adb_sh, find_adb, log  # noqa: E402

BOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "brave_google_bot.py")

# isim -> (wm_size, wm_density, ad, sinif)
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


def get_screen(adb, serial):
    import re
    sz = adb_sh(adb, serial, "shell", "wm", "size")
    dn = adb_sh(adb, serial, "shell", "wm", "density")
    # Override size üstünlük təşkil edir (Physical size-dan əvvəl gəlir)
    mo = re.search(r"Override size:\s*(\d+)x(\d+)", sz)
    if mo:
        size = f"{mo.group(1)}x{mo.group(2)}"
    else:
        mp = re.search(r"Physical size:\s*(\d+)x(\d+)", sz)
        size = f"{mp.group(1)}x{mp.group(2)}" if mp else "?"
    # Override density üstünlük təşkil edir (Physical density-dən əvvəl gəlir)
    mdo = re.search(r"Override density:\s*(\d+)", dn)
    if mdo:
        density = int(mdo.group(1))
    else:
        md = re.search(r"(\d+)", dn)
        density = int(md.group(1)) if md else 0
    return size, density


def apply_screen(adb, serial, size, density):
    adb_sh(adb, serial, "shell", "wm", "size", size)
    adb_sh(adb, serial, "shell", "wm", "density", str(density))
    time.sleep(1.5)


def reset_screen(adb, serial):
    adb_sh(adb, serial, "shell", "wm", "size", "reset")
    adb_sh(adb, serial, "shell", "wm", "density", "reset")
    time.sleep(1.0)


def main():
    p = argparse.ArgumentParser(
        description="Bot dövrünü fərqli ekran ölçülərində işə salır")
    p.add_argument("--query", default="turanly", help="Axtarış sözü")
    p.add_argument("--result", type=int, default=1, help="Necəncı nəticə")
    p.add_argument("--stay", type=float, default=8,
                   help="Səhifədə neçə saniyə qalsın")
    p.add_argument("--devices", default=",".join(DEFAULT_ORDER))
    p.add_argument("--udid", default=None)
    p.add_argument("--list", action="store_true")
    p.add_argument("--out", default=None)
    p.add_argument("--shots", action="store_true",
                   help="Bot skrinshotlarını da saxla")
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
        print("!! adb tapılmadı. `source scripts/env.sh` et.")
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
    out_dir = args.out or os.path.join("reports", "cycle", stamp)
    os.makedirs(out_dir, exist_ok=True)

    log(tag, f"Dövr başlayır: {len(names)} ekran ölçüsü")
    log(tag, f"Axtarış: '{args.query}' | Nəticə: #{args.result}")
    log(tag, f"Öncəki ekran: {orig_size} @ {orig_density}dpi")
    log(tag, f"Çıxış: {out_dir}")

    results = []
    try:
        for i, name in enumerate(names, 1):
            sz, dn, ad, tier = SCREEN_PRESETS[name]
            log(tag, f"")
            log(tag, f"━━━ [{i}/{len(names)}] {ad} ━━━ {sz} @{dn}dpi [{tier}]")
            apply_screen(adb, serial, sz, dn)
            cur_sz, cur_dn = get_screen(adb, serial)
            log(tag, f"   tətbiq olundu: {cur_sz} @ {cur_dn}dpi")

            # Botu subprocess kimi işə sal
            bot_cmd = [
                sys.executable, BOT, args.query,
                "--result", str(args.result),
                "--stay", str(args.stay),
                "--udid", serial,
                "--screen", sz,
                "--density", str(dn),
            ]
            if args.shots:
                bot_cmd += ["--shots", os.path.join(out_dir, name)]

            t0 = time.time()
            try:
                proc = subprocess.run(
                    bot_cmd, capture_output=True, text=True, timeout=300,
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                )
                dur = time.time() - t0
                bot_out = (proc.stdout + "\n" + proc.stderr).strip()
                ok = proc.returncode == 0

                # Bot çıxışını göstər (son 6 sətir)
                lines = [l for l in bot_out.splitlines() if l.strip()]
                for l in lines[-6:]:
                    log(tag, f"   | {l}")

                status = "OK" if ok else f"XETA(rc={proc.returncode})"
            except subprocess.TimeoutExpired:
                dur = time.time() - t0
                ok = False
                status = "TIMEOUT"
                bot_out = "300 san limiti aşdı"
                log(tag, "   | !! 300 san timeout")

            # Ekranı bərpa et (növbəti presetdən əvvəl)
            reset_screen(adb, serial)

            # Bot artıq özü reset edir (atexit), amma əminlik üçün
            results.append({
                "preset": name, "device": ad, "tier": tier,
                "wm_size": sz, "wm_density": dn,
                "status": status, "ok": ok,
                "duration_s": round(dur, 1),
            })
            log(tag, f"   status: {status} ({dur:.0f} san)")

            # Növbəti presetdən əvvəl qısa fasilə
            if i < len(names):
                time.sleep(2)

    finally:
        # Hər halda ekranı bərpa et
        reset_screen(adb, serial)
        sz, dn = get_screen(adb, serial)
        log(tag, f"")
        log(tag, f"Ekran bərpa olundu: {sz} @ {dn}dpi")

    # Hesabat
    rep = os.path.join(out_dir, "report.json")
    with open(rep, "w") as f:
        json.dump({
            "url": "google-search",
            "query": args.query,
            "device": model, "udid": serial,
            "orig_screen": {"size": orig_size, "density": orig_density},
            "when": stamp,
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"  DÖVR TAMAMLANDI")
    print(f"  Test: {len(results)} | Uğurlu: {sum(1 for r in results if r['ok'])}")
    for r in results:
        mark = "✅" if r["ok"] else "❌"
        print(f"  {mark} [{r['tier']:8s}] {r['device']:22s} "
              f"{r['wm_size']} @{r['wm_density']}dpi  {r['duration_s']}s")
    print(f"  Hesabat: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    main()
