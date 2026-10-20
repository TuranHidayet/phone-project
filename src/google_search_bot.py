#!/usr/bin/env python3
"""
Google axtaris botu (REAL Android telefonda, chromedriver + adb)
----------------------------------------------------------------
Telefonda Chrome-u acir -> google.com-a girir -> axtaris sozunu REAL klaviatura ile
yazir -> Enter -> neticelerden birincisine REAL barmaqla toxunur -> sehifeni gezir.

Istifade:
    source scripts/env.sh
    $PY src/google_search_bot.py telefon
    $PY src/google_search_bot.py "telefon qiymetleri" --result 2
    $PY src/google_search_bot.py telefon --udid 192.168.1.127:5555
"""

import sys
import time
import random
import argparse

from android_chrome_bot import (
    find_adb, adb_sh, detect_devices, device_profile, resolve_chromedriver,
    build_driver, tap_element, touch_scroll, log,
)

# Kuki/razilasq pencerelerinde EN GIZLILIK-QORUYUCU secim (redd et)
REJECT_TEXTS = (
    "reject all", "hamısını rədd et", "hamisini redd et",
    "отклонить все", "отклонить всё", "reject",
)


def dismiss_consent(driver, adb, serial, size, tag):
    """
    Google kuki razilasq pencresi cixarsa -- 'Hamisini redd et' secir
    (en gizlilik-qoruyucu variant). Yoxdursa sakitce kecir.
    """
    btn = driver.execute_script("""
        var want = arguments[0];
        var els = document.querySelectorAll('button, div[role="button"], a[role="button"]');
        for (var i = 0; i < els.length; i++) {
            var t = (els[i].innerText || '').trim().toLowerCase();
            if (!t) continue;
            for (var j = 0; j < want.length; j++) {
                if (t.indexOf(want[j]) !== -1) {
                    var r = els[i].getBoundingClientRect();
                    if (r.width > 8 && r.height > 8) return els[i];
                }
            }
        }
        return null;
    """, list(REJECT_TEXTS))
    if btn is None:
        return False
    log(tag, "        kuki pencresi: 'redd et' secilir")
    ok, _ = tap_element(driver, adb, serial, size, btn)
    if not ok:
        driver.execute_script("arguments[0].click();", btn)
    time.sleep(random.uniform(1.5, 2.5))
    return True


def looks_like_captcha(driver):
    """Google bot yoxlamasi (CAPTCHA) cixibsa -- dayanmaq lazimdir."""
    return driver.execute_script("""
        var u = location.href, b = document.body ? document.body.innerText : '';
        return u.indexOf('/sorry/') !== -1 ||
               b.indexOf('unusual traffic') !== -1 ||
               b.indexOf('Мы зарегистрировали подозрительный трафик') !== -1;
    """)


def type_query(driver, adb, serial, size, tag, query):
    """Axtaris xanasina toxunur ve REAL klaviatura ile yazir."""
    box = driver.execute_script("""
        return document.querySelector('textarea[name="q"]') ||
               document.querySelector('input[name="q"]');
    """)
    if box is None:
        return False
    ok, why = tap_element(driver, adb, serial, size, box)
    if not ok:
        log(tag, f"        xanaya toxunulmadi ({why}) -- JS focus")
        driver.execute_script("arguments[0].focus();", box)
    time.sleep(random.uniform(0.8, 1.4))

    # Insan kimi: sozu hisse-hisse yazir
    for chunk in [query[i:i + 3] for i in range(0, len(query), 3)]:
        adb_sh(adb, serial, "shell", "input", "text", chunk.replace(" ", "%s"))
        time.sleep(random.uniform(0.15, 0.45))
    time.sleep(random.uniform(0.5, 1.0))
    adb_sh(adb, serial, "shell", "input", "keyevent", "66")   # Enter
    return True


def collect_results(driver):
    """Organik netice linkleri (reklamlar ve Google daxili linkler atilir)."""
    return driver.execute_script("""
        var out = [], seen = {};
        var hs = document.querySelectorAll('#search h3, #rso h3');
        for (var i = 0; i < hs.length; i++) {
            var a = hs[i].closest('a');
            if (!a || !a.href) continue;
            var h = a.href;
            if (h.indexOf('google.com') !== -1 || h.indexOf('/aclk') !== -1) continue;
            if (!/^https?:/.test(h) || seen[h]) continue;
            var r = a.getBoundingClientRect();
            seen[h] = 1;
            out.push({href: h, text: (hs[i].innerText || '').trim().slice(0, 70),
                      idx: i, tappable: r.width > 8 && r.height > 8});
        }
        return out;
    """)


def main():
    p = argparse.ArgumentParser(description="Google axtaris botu (real Android)")
    p.add_argument("query", nargs="?", default="telefon", help="Axtaris sozu")
    p.add_argument("--result", type=int, default=1, help="Necenci netice acilsin (default 1)")
    p.add_argument("--udid", help="Cihaz serial/IP:port")
    p.add_argument("--stay", type=float, default=12, help="Acilan sehifede nece saniye qalsin")
    args = p.parse_args()

    adb = find_adb()
    if not adb:
        print("XETA: adb tapilmadi. `source scripts/env.sh` et.")
        sys.exit(1)

    ready, problems = detect_devices(adb)
    for s, state in problems:
        print(f"XEBERDARLIQ: {s} -> '{state}'")
    if not ready:
        print("XETA: qosulu Android cihaz yoxdur.")
        sys.exit(1)

    serial = args.udid if args.udid else ready[0]
    if serial not in ready:
        print(f"XETA: {serial} hazir deyil. Qosulular: {', '.join(ready)}")
        sys.exit(1)

    prof = device_profile(adb, serial)
    tag = prof["model"] or serial
    size = prof["size"]
    print(f"=== {prof['model']} | Android {prof['android']} | "
          f"{size[0]}x{size[1]} | Chrome {prof['chrome']} ===\n")
    if not prof["chrome"]:
        print("XETA: telefonda Chrome yoxdur.")
        sys.exit(1)

    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
    driver = build_driver(serial, resolve_chromedriver(prof["chrome"]))
    try:
        log(tag, "Google acilir...")
        driver.get("https://www.google.com")
        time.sleep(random.uniform(2.0, 3.5))
        dismiss_consent(driver, adb, serial, size, tag)

        if looks_like_captcha(driver):
            log(tag, "!! Google bot yoxlamasi (CAPTCHA) cixdi -- dayanilir.")
            log(tag, "   Bunu avtomatik kecmek olmaz; telefonda el ile hell etmek lazimdir.")
            return

        log(tag, f"Axtarilir: '{args.query}'")
        if not type_query(driver, adb, serial, size, tag, args.query):
            log(tag, "!! Axtaris xanasi tapilmadi.")
            return
        time.sleep(random.uniform(3.0, 4.5))
        dismiss_consent(driver, adb, serial, size, tag)

        if looks_like_captcha(driver):
            log(tag, "!! Netice sehifesinde CAPTCHA cixdi -- dayanilir.")
            return

        results = collect_results(driver)
        if not results:
            log(tag, "!! Netice tapilmadi (sehife strukturu deyisib ola biler).")
            log(tag, f"   URL: {driver.current_url}")
            return

        log(tag, f"{len(results)} netice tapildi. Ilk 3:")
        for i, r in enumerate(results[:3], 1):
            log(tag, f"   {i}. {r['text']}  ->  {r['href'][:70]}")

        n = max(1, min(args.result, len(results)))
        target = results[n - 1]
        log(tag, f"-> {n}-ci neticeye toxunur: '{target['text']}'")

        before = driver.current_url
        el = driver.execute_script("""
            var hs = document.querySelectorAll('#search h3, #rso h3');
            return hs[arguments[0]] ? hs[arguments[0]].closest('a') : null;
        """, target["idx"])

        moved = False
        if el is not None:
            ok, why = tap_element(driver, adb, serial, size, el)
            log(tag, f"   toxundu {why}" if ok else f"   toxunulmadi: {why}")
            deadline = time.time() + 15
            while time.time() < deadline:
                if driver.current_url != before:
                    moved = True
                    break
                time.sleep(0.5)
        if not moved:
            log(tag, "   (naviqasiya olmadi -- birbasa acilir)")
            driver.get(target["href"])
        time.sleep(random.uniform(2.5, 4.0))

        log(tag, f"AÇILDI: {driver.title}")
        log(tag, f"   URL:  {driver.current_url}")

        touch_scroll(adb, serial, size, steps=random.randint(3, 6))
        time.sleep(args.stay)
        log(tag, f"   movqe: {driver.execute_script('return Math.round(window.scrollY)')}px "
                 f"/ {driver.execute_script('return document.body.scrollHeight')}px")
        log(tag, "Bitdi ✅")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
