#!/usr/bin/env python3
"""
Firefox scroll bot (Playwright)
--------------------------------
Firefox açır -> verilən sayta girir -> insan kimi scroll edir -> baglanir.

İstifadə:
    python3 firefox_scroll_bot.py https://senin-saytin.com
    python3 firefox_scroll_bot.py https://senin-saytin.com --visits 3 --headless

Qeyd: Yalniz oz saytinizda / icaze verilen saytlarda istifade edin.
"""

import sys
import time
import random
import argparse
from playwright.sync_api import sync_playwright

# ------------------ AYARLAR (default) ------------------
DEFAULT_URL      = "https://example.com"   # arqument verilmese bu isledilir
VISITS           = 1        # neçe defe girsin
HEADLESS         = False    # True = brauzer görünmesin (gizli), False = görünsün
MIN_STAY_SEC     = 6        # sehifede minimum qalma vaxti (saniye)
MAX_STAY_SEC     = 14       # sehifede maksimum qalma vaxti (saniye)
SCROLL_STEPS_MIN = 6        # minimum neçe defe scroll etsin
SCROLL_STEPS_MAX = 14       # maksimum neçe defe scroll etsin

# iPhone emulyasiyasi (--mobile ile ise dusur)
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.5 Mobile/15E148 Safari/604.1")
IPHONE_VIEWPORT = {"width": 390, "height": 844}   # iPhone ölçüsü
DESKTOP_VIEWPORT = {"width": 1280, "height": 800}
# -------------------------------------------------------


def human_scroll(page):
    """Sehife boyunca teleseden, tesadufi addimlarla asagi-yuxari scroll edir."""
    steps = random.randint(SCROLL_STEPS_MIN, SCROLL_STEPS_MAX)
    for i in range(steps):
        # her defe 300-900 px asagi
        dy = random.randint(300, 900)
        page.mouse.wheel(0, dy)
        # insan kimi qisa fasile
        time.sleep(random.uniform(0.6, 2.2))

    # bezen bir az geri yuxari qalxsin (real istifadeçi kimi)
    if random.random() < 0.6:
        for _ in range(random.randint(2, 4)):
            page.mouse.wheel(0, -random.randint(200, 600))
            time.sleep(random.uniform(0.4, 1.2))


def one_visit(pw, url, headless, mobile=False):
    browser = pw.firefox.launch(headless=headless)
    if mobile:
        context = browser.new_context(
            viewport=IPHONE_VIEWPORT,
            user_agent=IPHONE_UA,
            locale="az-AZ",
        )
    else:
        context = browser.new_context(
            viewport=DESKTOP_VIEWPORT,
            locale="az-AZ",
        )
    page = context.new_page()
    try:
        rejim = "iPhone (mobil)" if mobile else "Masaüstü"
        print(f"  -> Rejim: {rejim}")
        print(f"  -> Açilir: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=45000)

        # sehifenin yuklenmesine qisa fasile
        time.sleep(random.uniform(1.5, 3.0))

        # scroll et
        human_scroll(page)

        # bir az sehifede qal
        stay = random.uniform(MIN_STAY_SEC, MAX_STAY_SEC)
        print(f"  -> Scroll bitdi, {stay:.1f} saniye qalir...")
        time.sleep(stay)

    except Exception as e:
        print(f"  !! Xeta: {e}")
    finally:
        context.close()
        browser.close()
        print("  -> Baglandi.")


def main():
    parser = argparse.ArgumentParser(description="Firefox scroll bot")
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="Saytin ünvani")
    parser.add_argument("--visits", type=int, default=VISITS, help="Neçe defe girsin")
    parser.add_argument("--headless", action="store_true", help="Brauzer görünmesin")
    parser.add_argument("--mobile", action="store_true", help="iPhone kimi (mobil) ac")
    args = parser.parse_args()

    if args.url == DEFAULT_URL:
        print("XEBERDARLIQ: URL verilmedi, default 'example.com' isledilir.")
        print("Düzgün istifade: python3 firefox_scroll_bot.py https://senin-saytin.com\n")

    with sync_playwright() as pw:
        for i in range(args.visits):
            print(f"[{i+1}/{args.visits}] Ziyaret basladi")
            one_visit(pw, args.url, args.headless, args.mobile)
            # ziyaretler arasi fasile
            if i < args.visits - 1:
                pause = random.uniform(3, 8)
                print(f"...{pause:.1f} saniye gözlenir...\n")
                time.sleep(pause)

    print("\nHamisi bitdi ✅")


if __name__ == "__main__":
    main()
