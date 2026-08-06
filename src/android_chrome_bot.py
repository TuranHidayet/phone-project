#!/usr/bin/env python3
"""
Real Android Chrome bot (chromedriver + adb) -- COX CIHAZ PARALEL
------------------------------------------------------------------
Qosulu REAL Android telefonlarda Chrome-u acir -> sayta girir -> insan kimi scroll edir
-> daxili linklere REAL barmaqla toxunub bir nece sehifede gezir -> baglanir.
Bir nece telefon qosulubsa hamisinda EYNI VAXTDA (paralel) isleyir.

NIYE APPIUM DEYIL:
  Xiaomi/MIUI "Install via USB"-ni bloklayir (INSTALL_FAILED_USER_RESTRICTED), ona gore
  Appium oz komekci APK-larini qura bilmir. chromedriver ise telefondaki Chrome-a
  birbasa adb uzerinden qosulur -- hec ne qurulmur, Appium server de lazim deyil.

TELEB OLUNUR (her telefonda):
  1) Developer options + USB debugging aciq
  2) `adb devices` telefonu "device" kimi gosterir
  (Mi hesabi / Install via USB LAZIM DEYIL)

İstifade:
    source scripts/env.sh
    $PY src/android_chrome_bot.py https://turanly.com                 # bir cihaz
    $PY src/android_chrome_bot.py https://turanly.com --all           # BUTUN cihazlar paralel
    $PY src/android_chrome_bot.py https://turanly.com --all --pages 6 --visits 2
    $PY src/android_chrome_bot.py https://turanly.com --udid AAA,BBB  # secilmis cihazlar
    $PY src/android_chrome_bot.py --list                              # cihazlari sadala
"""

import os
import re
import sys
import json
import time
import random
import argparse
import threading
import subprocess
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

# ------------------ AYARLAR ------------------
CHROME_PKG        = "com.android.chrome"
PAGES             = 4          # bir ziyaretde nece sehife gezsin
PAGE_STAY_MIN     = 5          # her sehifede minimum qalma (saniye)
PAGE_STAY_MAX     = 14
SCROLL_STEPS_MIN  = 3          # her sehifede scroll addimi
SCROLL_STEPS_MAX  = 9
BACK_CHANCE       = 0.20       # bezen "geri" duymesine bassin (real istifadeci kimi)
PAGE_LOAD_TIMEOUT = 60
NAV_WAIT_SEC      = 12         # klikden sonra URL deyismesini nece gozlesin
START_STAGGER_SEC = 4          # cihazlar eyni saniyede baslamasin (tebii gorunsun)

# mobil naviqasiya menyusunu acan duymeler
MENU_SELECTORS = (
    "button[aria-label*='menu' i]", "button[aria-label*='navigation' i]",
    "[class*='burger']", "[class*='hamburger']",
    "[class*='menu-toggle']", "[class*='nav-toggle']",
    "button[aria-expanded]",
)
# ---------------------------------------------

_print_lock = threading.Lock()


def log(tag, msg):
    with _print_lock:
        print(f"[{tag}] {msg}", flush=True)


# ============ adb / cihaz ============

def find_adb():
    """adb-ni PATH-de ve ya Android SDK icinde tapir."""
    from shutil import which
    candidates = [
        os.environ.get("ADB"),
        os.path.join(os.environ.get("ANDROID_HOME", ""), "platform-tools", "adb"),
        os.path.join(os.environ.get("ANDROID_SDK_ROOT", ""), "platform-tools", "adb"),
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/opt/homebrew/bin/adb",
        "/usr/local/bin/adb",
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return which("adb")


def adb_sh(adb, serial, *args):
    r = subprocess.run([adb, "-s", serial, *args], capture_output=True, text=True)
    return r.stdout.strip()


def detect_devices(adb):
    """(hazir seriallar, problemli cihazlar) qaytarir."""
    out = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    ready, problems = [], []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        if state == "device":
            ready.append(serial)
        else:
            problems.append((serial, state))
    return ready, problems


def device_profile(adb, serial):
    """Cihaz haqqinda lazim olan her sey: model, android, ekran, Chrome versiyasi."""
    model = adb_sh(adb, serial, "shell", "getprop", "ro.product.model") or serial
    android = adb_sh(adb, serial, "shell", "getprop", "ro.build.version.release")
    m = re.search(r"(\d+)x(\d+)", adb_sh(adb, serial, "shell", "wm", "size"))
    size = (int(m.group(1)), int(m.group(2))) if m else (1080, 1920)
    dump = adb_sh(adb, serial, "shell", "dumpsys", "package", CHROME_PKG)
    cm = re.search(r"versionName=([\d.]+)", dump)
    return {"serial": serial, "model": model, "android": android,
            "size": size, "chrome": cm.group(1) if cm else None}


def make_tags(profiles):
    """Her cihaza qisa, tekrarlanmayan etiket verir (log-larda prefiks kimi)."""
    tags, used = {}, {}
    for p in profiles:
        base = (p["model"] or p["serial"])[:14]
        used[base] = used.get(base, 0) + 1
        tags[p["serial"]] = base if used[base] == 1 else f"{base}#{used[base]}"
    return tags


# ============ chromedriver ============

def resolve_chromedriver(version):
    """Chrome versiyasina uygun chromedriver-i Selenium Manager ile tapir/yukleyir."""
    import selenium
    sm = os.path.join(os.path.dirname(selenium.__file__),
                      "webdriver", "common", "macos", "selenium-manager")
    if not os.path.isfile(sm):
        return None
    cmd = [sm, "--browser", "chrome", "--output", "json"]
    if version:
        cmd += ["--browser-version", version.split(".")[0]]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)["result"]["driver_path"]
    except Exception:
        return None


def build_driver(serial, driver_path):
    opts = webdriver.ChromeOptions()
    opts.add_experimental_option("androidPackage", CHROME_PKG)
    opts.add_experimental_option("androidDeviceSerial", serial)
    # Service() bos port-u ozu secir -> cihazlar paralel iseleyende toqquşma olmur
    svc = Service(executable_path=driver_path) if driver_path else Service()
    d = webdriver.Chrome(service=svc, options=opts)
    d.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return d


# ============ toxunus (real barmaq) ============

def wait_stable(driver, tries=10, pause=0.25):
    """
    Chrome-un ust paneli scroll-dan sonra gizlenir, yuxari scroll-da geri gelir --
    bu zaman mezmun ~150px surusur. Koordinat goturmeden EVVEL olculer
    sabitlesene qeder gozleyirik, yoxsa toxunus bosa dusur.
    """
    prev, m = None, None
    for _ in range(tries):
        m = driver.execute_script("""
            var vv = window.visualViewport;
            return {dpr: window.devicePixelRatio,
                    vh: vv ? vv.height : window.innerHeight,
                    ot: vv ? vv.offsetTop : 0,
                    sy: Math.round(window.scrollY)};
        """)
        cur = (m["vh"], m["ot"], m["sy"])
        if cur == prev:
            break
        prev = cur
        time.sleep(pause)
    return m


def tap_element(driver, adb, serial, size, el):
    """
    Elementi ekrana getirir ve REAL barmaqla (adb input tap) toxunur.
    (ugur, izah) qaytarir.
    """
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(random.uniform(0.4, 0.8))
    m = wait_stable(driver)

    dpr = m["dpr"] or 2
    top_offset = max(0, size[1] - m["vh"] * dpr)   # status bar + Chrome paneli

    # Toxunmazdan EVVEL yoxla: hemin nogtede hequeten bizim element var?
    probe = driver.execute_script("""
        var a = arguments[0], r = a.getBoundingClientRect();
        if (r.width < 3 || r.height < 3) return {ok: false, why: 'olcusuz/gizli'};
        var cx = r.left + r.width * arguments[1];
        var cy = r.top  + r.height * arguments[2];
        var vh = window.visualViewport ? window.visualViewport.height : innerHeight;
        if (cy < 0 || cy > vh) return {ok: false, why: 'ekranda deyil'};
        var hit = document.elementFromPoint(cx, cy);
        var mine = hit && (hit === a || a.contains(hit) ||
                          (hit.closest && (hit.closest('a') === a || hit.closest('button') === a)));
        return {ok: !!mine, why: mine ? '' : 'ustunu basqa element ortur', cx: cx, cy: cy};
    """, el, random.uniform(0.30, 0.70), random.uniform(0.35, 0.65))

    if not probe["ok"]:
        return False, probe["why"]

    dx = int(probe["cx"] * dpr)
    dy = int(probe["cy"] * dpr + top_offset)
    if not (0 < dx < size[0] and 0 <= dy < size[1]):
        return False, f"ekrandan kenar ({dx},{dy})"

    adb_sh(adb, serial, "shell", "input", "tap", str(dx), str(dy))
    return True, f"({dx},{dy})"


def touch_scroll(adb, serial, size, steps=None):
    """Real barmaq swipe-i (adb input swipe) -- OS seviyyesinde toxunus."""
    w, h = size
    steps = steps if steps is not None else random.randint(SCROLL_STEPS_MIN, SCROLL_STEPS_MAX)
    for _ in range(steps):
        x = int(w * random.uniform(0.40, 0.60))
        y1 = int(h * random.uniform(0.70, 0.80))
        y2 = int(h * random.uniform(0.25, 0.40))
        adb_sh(adb, serial, "shell", "input", "swipe",
               str(x), str(y1), str(x), str(y2), str(random.randint(220, 550)))
        time.sleep(random.uniform(0.6, 2.0))
    if random.random() < 0.5:
        for _ in range(random.randint(1, 3)):
            x = int(w * random.uniform(0.40, 0.60))
            adb_sh(adb, serial, "shell", "input", "swipe",
                   str(x), str(int(h * 0.35)), str(x), str(int(h * 0.65)),
                   str(random.randint(280, 600)))
            time.sleep(random.uniform(0.4, 1.0))


def js_scroll(driver, steps=None):
    """JS scroll -- deqiq, amma real toxunus hadisesi yaratmir."""
    steps = steps if steps is not None else random.randint(SCROLL_STEPS_MIN, SCROLL_STEPS_MAX)
    for _ in range(steps):
        driver.execute_script("window.scrollBy(0, arguments[0]);", random.randint(300, 800))
        time.sleep(random.uniform(0.6, 2.0))
    if random.random() < 0.5:
        for _ in range(random.randint(1, 3)):
            driver.execute_script("window.scrollBy(0, arguments[0]);", -random.randint(200, 500))
            time.sleep(random.uniform(0.4, 1.0))


# ============ link secimi ============

def same_site(host_a, host_b):
    return host_a.replace("www.", "") == host_b.replace("www.", "")


def collect_links(driver, base_host):
    """Sehifedeki DAXILI linkler (xarici saytlar, mailto, tel, # -- hamisi atilir)."""
    raw = driver.execute_script("""
        return [...document.querySelectorAll('a[href]')].map(function(a, i) {
            var r = a.getBoundingClientRect(), cs = getComputedStyle(a);
            // yigilmis mobil menyudaki linkler olcusuz olur -- onlara toxunmaq olmaz
            var tappable = r.width > 8 && r.height > 8 &&
                           cs.visibility !== 'hidden' && cs.display !== 'none' &&
                           parseFloat(cs.opacity) > 0.1;
            return {i: i, href: a.href,
                    text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 45),
                    tappable: tappable};
        });
    """)
    out, seen = [], set()
    for l in raw:
        href = (l.get("href") or "").split("#")[0].rstrip("/")
        if not href or not href.startswith(("http://", "https://")):
            continue
        if not same_site(urlparse(href).netloc, base_host):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append({"href": href, "text": l["text"], "idx": l["i"], "tappable": l["tappable"]})
    return out


def pick_link(links, visited):
    """Toxunula bilen ve hele gorulmemis linke ustunluk verir."""
    for pool in ([l for l in links if l["tappable"] and l["href"] not in visited],
                 [l for l in links if l["tappable"]],
                 [l for l in links if l["href"] not in visited],
                 links):
        if pool:
            return random.choice(pool)
    return None


def open_mobile_menu(driver, adb, serial, size):
    """
    Mobil naviqasiya menyusunu (hamburger) acmaga calisir.
    Sehifelerin coxunda daxili linkler mehz orada gizlenir -- acmasaq bot
    eyni bir-iki sehifede ilisib qalir.
    """
    btn = driver.execute_script("""
        var sels = arguments[0];
        for (var s = 0; s < sels.length; s++) {
            var els = document.querySelectorAll(sels[s]);
            for (var i = 0; i < els.length; i++) {
                var e = els[i], r = e.getBoundingClientRect(), cs = getComputedStyle(e);
                if (r.width > 8 && r.height > 8 && cs.visibility !== 'hidden' &&
                    cs.display !== 'none' && parseFloat(cs.opacity) > 0.1) return e;
            }
        }
        return null;
    """, list(MENU_SELECTORS))
    if btn is None:
        return False
    try:
        ok, _ = tap_element(driver, adb, serial, size, btn)
        if not ok:
            driver.execute_script("arguments[0].click();", btn)
        time.sleep(random.uniform(0.8, 1.5))
        return True
    except Exception:
        return False


# ============ gezinti ============

def browse(driver, adb, serial, tag, size, start_url, pages, use_js):
    """Sayta girir ve `pages` qeder sehifede insan kimi gezir. Gezilen yolu qaytarir."""
    base_host = urlparse(start_url).netloc
    visited, route = set(), []

    driver.get(start_url)
    time.sleep(random.uniform(2.0, 3.5))

    for n in range(1, pages + 1):
        visited.add(driver.current_url.split("#")[0].rstrip("/"))
        route.append(driver.title or driver.current_url)
        log(tag, f"[{n}/{pages}] {driver.title}")
        log(tag, f"        {driver.current_url}")

        # oxuyur: scroll + qalma
        if use_js:
            js_scroll(driver)
        else:
            touch_scroll(adb, serial, size)
        stay = random.uniform(PAGE_STAY_MIN, PAGE_STAY_MAX)
        log(tag, f"        scroll {driver.execute_script('return Math.round(window.scrollY)')}px"
                 f" / {driver.execute_script('return document.body.scrollHeight')}px"
                 f", {stay:.1f}s qalir")
        time.sleep(stay)

        if n == pages:
            break

        # bezen geri qayidir -- real istifadeci kimi
        if len(visited) > 1 and random.random() < BACK_CHANCE:
            log(tag, "        <- geri qayidir")
            adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(random.uniform(2.0, 3.5))
            continue

        links = collect_links(driver, base_host)
        # yeni toxunulasi link qalmayibsa menyunu acib naviqasiyani uze cixart
        if not [l for l in links if l["tappable"] and l["href"] not in visited]:
            if open_mobile_menu(driver, adb, serial, size):
                log(tag, "        (menyu acildi)")
                links = collect_links(driver, base_host)

        target = pick_link(links, visited)
        if not target:
            log(tag, "        (daxili link tapilmadi, dayanir)")
            break

        label = target["text"] or urlparse(target["href"]).path
        log(tag, f"        -> toxunur: '{label}'")
        before = driver.current_url

        el = None
        try:
            el = driver.execute_script(
                "return document.querySelectorAll('a[href]')[arguments[0]];", target["idx"])
        except Exception:
            pass

        def url_changed(timeout):
            deadline = time.time() + timeout
            base = before.split("#")[0].rstrip("/")
            while time.time() < deadline:
                if driver.current_url.split("#")[0].rstrip("/") != base:
                    return True
                time.sleep(0.4)
            return False

        # 1) REAL barmaq toxunusu
        moved = False
        if el is not None:
            try:
                tapped, why = tap_element(driver, adb, serial, size, el)
                if tapped:
                    moved = url_changed(NAV_WAIT_SEC)
                    log(tag, f"        toxundu {why}" + ("" if moved else " -- naviqasiya olmadi"))
                else:
                    log(tag, f"        toxunulmadi: {why}")
            except Exception as e:
                log(tag, f"        toxunus xetasi: {e}")

        # 2) ehtiyat: Selenium klik (bu da hequeti klikdir, referrer saxlanir)
        if not moved and el is not None:
            try:
                driver.execute_script("arguments[0].click();", el)
                moved = url_changed(NAV_WAIT_SEC)
                if moved:
                    log(tag, "        (klik ile kecdi)")
            except Exception:
                pass

        # 3) son care: birbasa naviqasiya
        if not moved:
            log(tag, "        (birbasa acilir)")
            driver.get(target["href"])
        time.sleep(random.uniform(1.5, 3.0))

    return route


def run_device(prof, tag, adb, driver_path, start_url, pages, visits, use_js):
    """Bir cihazda butun ziyaretleri icra edir. Oz sapinda (thread) islenir."""
    time.sleep(random.uniform(0, START_STAGGER_SEC))   # hamisi eyni anda baslamasin
    serial, size = prof["serial"], prof["size"]
    adb_sh(adb, serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP")

    ok, routes = 0, []
    for i in range(visits):
        log(tag, f"Ziyaret {i+1}/{visits} basladi ({pages} sehife)")
        driver = None
        try:
            driver = build_driver(serial, driver_path)
            route = browse(driver, adb, serial, tag, size, start_url, pages, use_js)
            routes.append(route)
            ok += 1
            log(tag, f"Marsrut: {' → '.join(r.split(' | ')[0] for r in route)}")
        except Exception as e:
            log(tag, f"!! Xeta: {type(e).__name__}: {str(e).splitlines()[0][:160]}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
        if i < visits - 1:
            pause = random.uniform(4, 10)
            log(tag, f"...{pause:.1f}s gozlenir")
            time.sleep(pause)

    log(tag, f"Bitdi: {ok}/{visits} ziyaret ugurlu")
    return {"tag": tag, "serial": serial, "model": prof["model"],
            "ok": ok, "visits": visits, "routes": routes}


def main():
    p = argparse.ArgumentParser(description="Android Chrome gezinti botu (cox cihaz, paralel)")
    p.add_argument("url", nargs="?", default="https://turanly.com", help="Baslangic unvani")
    p.add_argument("--pages", type=int, default=PAGES, help="Bir ziyaretde nece sehife gezsin")
    p.add_argument("--visits", type=int, default=1, help="Her cihaz nece defe bastan girsin")
    p.add_argument("--udid", help="Cihaz serial(lari), vergulle: AAA,BBB")
    p.add_argument("--all", action="store_true", help="BUTUN qosulu cihazlarda paralel isle")
    p.add_argument("--list", action="store_true", help="Qosulu cihazlari sadala ve cix")
    p.add_argument("--js", action="store_true", help="Real toxunus evezine JS scroll")
    p.add_argument("--stay", type=float, help="Her sehifede ortalama nece saniye qalsin")
    p.add_argument("--scrolls", type=int, help="Her sehifede nece scroll addimi")
    args = p.parse_args()

    # vaxt ayarlari (verilibse defaultlari evez edir)
    global PAGE_STAY_MIN, PAGE_STAY_MAX, SCROLL_STEPS_MIN, SCROLL_STEPS_MAX
    if args.stay is not None:
        PAGE_STAY_MIN, PAGE_STAY_MAX = args.stay * 0.7, args.stay * 1.3
    if args.scrolls is not None:
        SCROLL_STEPS_MIN = SCROLL_STEPS_MAX = max(0, args.scrolls)

    adb = find_adb()
    if not adb:
        print("XETA: adb tapilmadi. `source scripts/env.sh` et ve ya ANDROID_HOME teyin et.")
        sys.exit(1)

    ready, problems = detect_devices(adb)
    for s, state in problems:
        print(f"XEBERDARLIQ: {s} -> '{state}' (telefonda USB debugging icazesini tesdiqle)")
    if not ready:
        print("XETA: qosulu Android cihaz yoxdur (`adb devices` bosdur).")
        print("   Yoxla: USB rejimi 'File Transfer'-dedir? USB debugging aciqdir?")
        sys.exit(1)

    # hansi cihazlarda isleyek
    if args.udid:
        wanted = [u.strip() for u in args.udid.split(",") if u.strip()]
        missing = [u for u in wanted if u not in ready]
        if missing:
            print(f"XETA: bu cihaz(lar) hazir deyil: {', '.join(missing)}")
            sys.exit(1)
        chosen = wanted
    elif args.all or args.list:
        chosen = ready
    else:
        chosen = ready[:1]
        if len(ready) > 1:
            print(f"QEYD: {len(ready)} cihaz qosulub, yalniz birincisi isledilir. "
                  f"Hamisi ucun --all ver.")

    profiles = [device_profile(adb, s) for s in chosen]
    tags = make_tags(profiles)

    print(f"=== {len(profiles)} cihaz ===")
    for pr in profiles:
        print(f"  [{tags[pr['serial']]}] {pr['model']} | Android {pr['android']} | "
              f"{pr['size'][0]}x{pr['size'][1]} | Chrome {pr['chrome'] or 'YOXDUR'} | {pr['serial']}")
    if args.list:
        return

    usable = [pr for pr in profiles if pr["chrome"]]
    for pr in profiles:
        if not pr["chrome"]:
            print(f"ATLANIR [{tags[pr['serial']]}]: Chrome ({CHROME_PKG}) qurulmayib.")
    if not usable:
        print("XETA: hec bir cihazda Chrome yoxdur.")
        sys.exit(1)

    # chromedriver-i major versiya uzre bir defe hell et (paralel yuklemede toqqusma olmasin)
    drivers = {}
    for pr in usable:
        major = pr["chrome"].split(".")[0]
        if major not in drivers:
            drivers[major] = resolve_chromedriver(pr["chrome"])
            print(f"chromedriver (Chrome {major}): {drivers[major] or 'avtomatik'}")

    print(f"\n=== Basladi: {args.url} | {args.pages} sehife | {args.visits} ziyaret ===\n")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(usable)) as ex:
        futures = [ex.submit(run_device, pr, tags[pr["serial"]], adb,
                             drivers[pr["chrome"].split(".")[0]],
                             args.url, args.pages, args.visits, args.js)
                   for pr in usable]
        results = [f.result() for f in futures]

    print(f"\n=== YEKUN ({time.time()-t0:.0f}s) ===")
    total_ok = total = 0
    for r in results:
        total_ok += r["ok"]
        total += r["visits"]
        pages_seen = sum(len(rt) for rt in r["routes"])
        mark = "✅" if r["ok"] == r["visits"] else "⚠️"
        print(f"  {mark} [{r['tag']}] {r['ok']}/{r['visits']} ziyaret, {pages_seen} sehife")
    print(f"  Cemi: {total_ok}/{total} ziyaret ugurlu")


if __name__ == "__main__":
    main()
