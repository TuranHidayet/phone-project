#!/usr/bin/env python3
"""
Sayti "ferqli cihaz" kimi gosterir -- telefonda gezende sayt (ve saytdaki
her hansı script) fərqli nüvə sayı, RAM, model ve ekran olcusu gorur.

Bu, Mac-de isleyen Chrome DevTools Protocol (CDP) uzerinden isleyir:
  adb forward tcp:9222 localabstract:chrome_devtools_remote_<pid>
  (Brave = Chromium, DevTools socket-i artiq aciqdir)

Deyisen 3 shey:
  1. User-Agent          -> cihaz modeli + OS
  2. viewport + DPR      -> ekran olcusu (Emulation.setDeviceMetricsOverride)
  3. navigator.hardwareConcurrency / navigator.deviceMemory -> nuve + RAM

QEWNET: bu yalniz test ucundur. Telefonda normal brauzer kimi isledende
spoof quvvede deyil (cevre degisikliyi reset olunur).

Istifade:
  $PY src/device_spoof.py https://turanly.com
  $PY src/device_spoof.py https://turanly.com --devices weak,mid,strong
  $PY src/device_spoof.py --list
  $PY src/device_spoof.py https://turanly.com --cores 2 --ram 1 --size 360x640
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from android_chrome_bot import adb_sh, find_adb, log  # noqa: E402

BRAVE_PKG = "com.brave.browser"
CHROME_VER = "152.0.7977.83"

ANDROID_UA = (
    "Mozilla/5.0 (Linux; Android {ver}; {model}) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/{cv} Mobile Safari/537.36"
)
SAFARI_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS {ver} like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/{sver} Mobile/15E148 Safari/604.1"
)
DESKTOP_UA = (
    "Mozilla/5.0 ({os}; {arch}) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/{cv} Safari/537.36"
)

# isim -> (nuve, ram_gb, w, h, dpr, platform, ua, ad, sinif)
# ad = cihaz modeli, sinif = budget/mid/flagship
PRESETS = {
    "galaxy-a05": (
        8, 4, 360, 800, 2, "Linux armv81",
        ANDROID_UA.format(ver="14", model="SM-A055F", cv=CHROME_VER),
        "Samsung Galaxy A05", "budget"),
    "redmi-12c": (
        8, 3, 392, 873, 2.75, "Linux armv81",
        ANDROID_UA.format(ver="13", model="22101316UG", cv=CHROME_VER),
        "Xiaomi Redmi 12C", "budget"),
    "galaxy-a54": (
        8, 6, 360, 780, 3, "Linux armv81",
        ANDROID_UA.format(ver="13", model="SM-A546B", cv=CHROME_VER),
        "Samsung Galaxy A54 5G", "mid"),
    "iphone-se3": (
        6, 4, 375, 667, 2, "iPhone",
        SAFARI_UA.format(ver="15_4", sver="15.4"),
        "iPhone SE (3rd gen)", "mid"),
    "pixel-7": (
        8, 8, 412, 915, 2.625, "Linux armv81",
        ANDROID_UA.format(ver="13", model="Pixel 7", cv=CHROME_VER),
        "Google Pixel 7", "flagship"),
    "iphone-14-pro": (
        6, 6, 393, 852, 3, "iPhone",
        SAFARI_UA.format(ver="16_0", sver="16.0"),
        "iPhone 14 Pro", "flagship"),
    "desktop-win": (
        12, 16, 1440, 900, 1, "Windows",
        DESKTOP_UA.format(os="Windows NT 10.0; Win64", arch="x64",
                          cv=CHROME_VER),
        "Desktop Windows", "desktop"),
}
DEFAULT_DEVICES = ["galaxy-a05", "redmi-12c", "galaxy-a54",
                   "iphone-se3", "pixel-7", "iphone-14-pro"]


# ---------------- DevTools socket / forward ----------------

def find_socket(adb, serial):
    out = adb_sh(adb, serial, "shell",
                 "cat /proc/net/unix | grep -o 'chrome_devtools_remote[^ ]*'")
    for line in out.split():
        line = line.strip()
        if "chrome_devtools_remote" in line:
            return line
    return None


def ensure_forward(adb, serial, local_port=9222):
    sock = find_socket(adb, serial)
    if not sock:
        raise RuntimeError("Brave DevTools socket tapilmadi (brauzer aciq olmalidir)")
    adb_sh(adb, serial, "forward", "--remove", f"tcp:{local_port}")
    adb_sh(adb, serial, "forward", f"tcp:{local_port}",
           f"localabstract:{sock}")
    time.sleep(0.6)
    return sock


# ---------------- CDP ----------------

def cdp_connect(port, url_part):
    import websocket
    tabs = json.load(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=6))
    page = None
    for t in tabs:
        if t.get("type") == "page" and url_part in (t.get("url") or ""):
            page = t
            break
    if page is None:
        for t in tabs:
            if t.get("type") == "page":
                page = t
                break
    if page is None:
        raise RuntimeError("Brave-da hec bir tab yoxdur")
    ws = websocket.create_connection(page["webSocketDebuggerUrl"],
                                     timeout=20, suppress_origin=True)
    return ws, page


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self._i = 0

    def send(self, method, **params):
        self._i += 1
        i = self._i
        self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == i:
                return r.get("result", {}) or {}

    def eval_js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True)
        res = r.get("result", {})
        if res.get("subtype") == "error":
            return {"__error__": res.get("description", "error")}
        return res.get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def spoof_script(cores, ram):
    """Hər səhifə yüklənməsindən əvvəl işə düşür -- refresh/link keçidində də qalır."""
    return f"""
(() => {{
  const C = {int(cores)}, R = {int(ram)};
  try {{
    Object.defineProperty(Navigator.prototype, 'hardwareConcurrency',
      {{ get: () => C, configurable: true, enumerable: true }});
  }} catch (e) {{}}
  try {{
    Object.defineProperty(Navigator.prototype, 'deviceMemory',
      {{ get: () => R, configurable: true, enumerable: true }});
  }} catch (e) {{}}
  try {{
    Object.defineProperty(Navigator.prototype, 'webdriver',
      {{ get: () => false, configurable: true, enumerable: true }});
  }} catch (e) {{}}
}})();
"""


def screenshot_b64(cdp):
    r = cdp.send("Page.captureScreenshot", format="png",
                 captureBeyondViewport=False)
    return r.get("data")


def open_url(adb, serial, url, wait=5.0):
    adb_sh(adb, serial, "shell", "am", "start", "-a",
           "android.intent.action.VIEW", "-d", url, "-p", BRAVE_PKG,
           "--activity-clear-top", "--es",
           "com.android.browser.application_id", BRAVE_PKG)
    time.sleep(random.uniform(wait, wait + 1.2))


# ---------------- əsas test ----------------

def apply_and_measure(adb, serial, port, url, name, cores, ram, w, h, dpr,
                      platform, ua, ad, sinif, out_dir, tag):
    open_url(adb, serial, url)
    ws, page = cdp_connect(port, url.split("//")[-1].split("/")[0])
    cdp = CDP(ws)
    try:
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Emulation.setUserAgentOverride",
                 userAgent=ua, platform=platform,
                 acceptLanguage="az-AZ,az;q=0.9,en;q=0.8")
        cdp.send("Emulation.setDeviceMetricsOverride",
                 width=w, height=h, deviceScaleFactor=dpr, mobile=True,
                 screenWidth=w, screenHeight=h)
        cdp.send("Page.addScriptToEvaluateOnNewDocument",
                 source=spoof_script(cores, ram))
        cdp.send("Page.reload", ignoreCache=True)
        time.sleep(7)

        seen = cdp.eval_js(
            "JSON.stringify({cores:navigator.hardwareConcurrency,"
            "ram:navigator.deviceMemory,"
            "vp:innerWidth+'x'+innerHeight,"
            "dpr:devicePixelRatio,"
            "ua:navigator.userAgent,"
            "title:document.title,"
            "href:location.href,"
            "mem:performance.memory?Math.round(performance.memory.usedJSHeapSize/1048576):null})")
        if isinstance(seen, str):
            seen = json.loads(seen)

        b64 = screenshot_b64(cdp)
        shot = None
        if b64:
            import base64
            shot = os.path.join(out_dir, f"{name}.png")
            with open(shot, "wb") as f:
                f.write(base64.b64decode(b64))

        log(tag, f"[{sinif}] {ad}")
        log(tag, f"  nuve={seen.get('cores')} ram={seen.get('ram')}GB "
                 f"| vp={seen.get('vp')} dpr={seen.get('dpr')} "
                 f"| js_heap={seen.get('mem')}MB")
        log(tag, f"  URL: {seen.get('href')}")

        return {
            "preset": name, "device": ad, "tier": sinif,
            "wanted": {"cores": cores, "ram": ram,
                       "size": f"{w}x{h}", "dpr": dpr},
            "seen_by_site": seen, "screenshot": shot, "status": "OK",
        }
    except Exception as e:
        log(tag, f"[{sinif}] {ad} XETA: {e}")
        return {"preset": name, "device": ad, "status": "XETA",
                "error": str(e)}
    finally:
        cdp.close()


def main():
    p = argparse.ArgumentParser(
        description="Sayti ferqli nuve/RAM/model/olcu ile goster")
    p.add_argument("url", nargs="?", default="https://turanly.com")
    p.add_argument("--udid", default=None)
    p.add_argument("--devices", default=",".join(DEFAULT_DEVICES))
    p.add_argument("--cores", type=int, default=None, help="Manual nuve sayi")
    p.add_argument("--ram", type=int, default=None, help="Manual RAM (GB)")
    p.add_argument("--size", default=None, help="Manual ekran, mes. 360x640")
    p.add_argument("--list", action="store_true")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    if args.list:
        for k, (c, r, w, h, d, pl, ua, ad, tier) in PRESETS.items():
            print(f"  {k:14s} {ad}")
            print(f"                 {c} nuve, {r} GB RAM, "
                  f"{w}x{h}@{d}dpr, sinif={tier}")
        return

    adb = find_adb()
    out = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    ready = [l.split()[0] for l in out.splitlines()[1:]
             if len(l.split()) == 2 and l.split()[1] == "device"]
    serial = args.udid or (ready[0] if ready else None)
    if not serial:
        print("!! Cihaz tapilmadi")
        sys.exit(1)
    model = adb_sh(adb, serial, "shell", "getprop", "ro.product.model") or serial
    tag = model

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out or os.path.join("reports", "spf", stamp)
    os.makedirs(out_dir, exist_ok=True)

    if args.cores or args.ram or args.size:
        w, h = (360, 640)
        if args.size:
            w, h = [int(x) for x in args.size.split("x")]
        combos = [dict(name="manual", cores=args.cores or 4,
                       ram=args.ram or 2, w=w, h=h, dpr=2,
                       platform="Linux armv81",
                       ua=ANDROID_UA.format(ver="12", model="Manual",
                                             cv=CHROME_VER),
                       ad="Manual", sinif="custom")]
    else:
        names = [n.strip() for n in args.devices.split(",") if n.strip()]
        bad = [n for n in names if n not in PRESETS]
        if bad:
            print(f"!! Namayum preset: {', '.join(bad)}. --list ile bax.")
            sys.exit(1)
        combos = [dict(name=n, cores=PRESETS[n][0], ram=PRESETS[n][1],
                       w=PRESETS[n][2], h=PRESETS[n][3], dpr=PRESETS[n][4],
                       platform=PRESETS[n][5], ua=PRESETS[n][6],
                       ad=PRESETS[n][7], sinif=PRESETS[n][8])
                  for n in names]

    log(tag, f"Device spoof: {args.url}")
    log(tag, f"Cixis: {out_dir}")

    ensure_forward(adb, serial, 9222)
    results = []
    try:
        for c in combos:
            r = apply_and_measure(adb, serial, 9222, args.url, c["name"],
                                  c["cores"], c["ram"], c["w"], c["h"],
                                  c["dpr"], c["platform"], c["ua"],
                                  c["ad"], c["sinif"], out_dir, tag)
            results.append(r)
    finally:
        adb_sh(adb, serial, "forward", "--remove", "tcp:9222")

    rep = os.path.join(out_dir, "report.json")
    with open(rep, "w") as f:
        json.dump({"url": args.url, "device": model, "udid": serial,
                   "when": stamp, "results": results}, f, indent=2,
                  ensure_ascii=False)

    print("\n=== XULASA ===")
    ok = [r for r in results if r.get("status") == "OK"]
    print(f"  test: {len(results)} | ugurlu: {len(ok)}")
    for r in ok:
        s = r.get("seen_by_site", {})
        print(f"  [{r.get('tier','?'):8s}] {r.get('device',r['preset'])}")
        print(f"           nuve={s.get('cores')} ram={s.get('ram')}GB "
              f"vp={s.get('vp')} dpr={s.get('dpr')}")
    print(f"  Skrinshotlar: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    main()
