#!/usr/bin/env python3
"""
Real iPhone Safari bot (Appium + XCUITest)
------------------------------------------
Qosulu REAL iPhone-da Safari-ni acir -> sayta girir -> insan kimi scroll edir -> baglanir.

TELEB OLUNUR (skriptden EVVEL):
  1) Appium server isleyir:            appium
  2) iPhone-da Developer Mode aciqdir
  3) Xcode-a Apple ID elave edilib
  4) Asagidaki TEAM_ID doldurulub (Apple Team ID, 10 simvol)

İstifade:
    python3 iphone_safari_bot.py https://turanly.com
"""

import sys
import time
import random
from appium import webdriver
from appium.options.ios import XCUITestOptions

# ------------------ AYARLAR ------------------
UDID       = "00008150-0012183E1103401C"   # qosulu iPhone-un UDID-i
DEVICE     = "Azerbaijan"                   # cihaz adi
TEAM_ID    = "QP92GY2683"                   # Apple Team ID (turanhidayatov@gmail.com)
APPIUM_URL = "http://127.0.0.1:4723"

MIN_STAY_SEC     = 8
MAX_STAY_SEC     = 16
SCROLL_STEPS_MIN = 6
SCROLL_STEPS_MAX = 14
# ---------------------------------------------


def build_driver():
    opts = XCUITestOptions()
    opts.platform_name = "iOS"
    opts.automation_name = "XCUITest"
    opts.udid = UDID
    opts.device_name = DEVICE
    opts.browser_name = "Safari"          # Safari-ni web rejiminde ac
    # WDA-ni Appium ozu qursun ve imzalasin:
    opts.set_capability("xcodeOrgId", TEAM_ID)
    opts.set_capability("xcodeSigningId", "Apple Development")
    opts.set_capability("updatedWDABundleId", f"com.appium.WebDriverAgentRunner")
    opts.set_capability("showXcodeLog", True)
    opts.set_capability("wdaLaunchTimeout", 120000)
    opts.set_capability("wdaConnectionTimeout", 120000)
    return webdriver.Remote(APPIUM_URL, options=opts)


def human_scroll(driver):
    steps = random.randint(SCROLL_STEPS_MIN, SCROLL_STEPS_MAX)
    for _ in range(steps):
        dy = random.randint(300, 800)
        driver.execute_script("window.scrollBy(0, arguments[0]);", dy)
        time.sleep(random.uniform(0.6, 2.0))
    if random.random() < 0.6:
        for _ in range(random.randint(2, 4)):
            driver.execute_script("window.scrollBy(0, arguments[0]);", -random.randint(200, 500))
            time.sleep(random.uniform(0.4, 1.0))


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://turanly.com"
    if TEAM_ID == "PUT_YOUR_TEAM_ID_HERE":
        print("XETA: TEAM_ID doldurulmayib. Xcode > Settings > Accounts-dan Team ID-ni yaz.")
        sys.exit(1)

    print(f"-> Appium-a qosulur, Safari acilir (real iPhone): {DEVICE}")
    driver = build_driver()
    try:
        print(f"-> Sayta girir: {url}")
        driver.get(url)
        time.sleep(random.uniform(2.0, 3.5))

        print("-> Scroll edir...")
        human_scroll(driver)

        stay = random.uniform(MIN_STAY_SEC, MAX_STAY_SEC)
        print(f"-> {stay:.1f} saniye qalir...")
        time.sleep(stay)
    except Exception as e:
        print(f"!! Xeta: {e}")
    finally:
        driver.quit()
        print("-> Safari baglandi. Bitdi ✅")


if __name__ == "__main__":
    main()
