# phone-project

Öz saytını (turanly.com) test etmək üçün brauzer-avtomatlaşdırma botları.
İki rejim var:

1. **Firefox bot** (`src/firefox_bot.py`) — Mac-da Playwright + Firefox ilə işləyir.
   Masaüstü və ya iPhone **emulyasiya** rejimi (mobil ekran + iOS user-agent).
2. **iPhone Safari bot** (`src/iphone_safari_bot.py`) — USB ilə qoşulu **REAL iPhone**-da
   Safari-ni Appium + XCUITest ilə sürür.
3. **Android Chrome bot** (`src/android_chrome_bot.py`) — USB ilə qoşulu **REAL Android**
   telefonda Chrome-u chromedriver + adb ilə sürür. **Appium lazım deyil.**

> **Qeyd:** Bu maşında `python3` (3.14) sistem-idarəlidir və paket qəbul etmir.
> Appium client / Playwright **`/usr/bin/python3`** (3.9) içindədir — botları onunla işlət,
> və ya əvvəlcə `source scripts/env.sh` edib `$PY` dəyişənini istifadə et.

---

## Struktur

```
phone-project/
├── README.md
├── requirements.txt          # Python asılılıqları
├── .gitignore
├── src/
│   ├── firefox_bot.py        # emulyasiya (Playwright/Firefox)
│   ├── iphone_safari_bot.py  # real iPhone (Appium/XCUITest)
│   └── android_chrome_bot.py # real Android (Appium/UiAutomator2)
├── scripts/
│   ├── env.sh                # PATH, ANDROID_HOME, $PY  (source ilə yüklə)
│   ├── start_appium.sh       # Appium serveri (iOS)
│   ├── start_appium_android.sh # Appium serveri (Android — normal halda LAZIM DEYİL)
│   └── start_tunnel.sh       # iOS 17+ RemoteXPC tunnel (sudo)
└── logs/                     # server logları (git-ə düşmür)
```

---

## 1) Firefox bot (emulyasiya)

Qurmaq (bir dəfə):
```bash
pip3 install --user playwright
python3 -m playwright install firefox
```

İşə salmaq:
```bash
# masaüstü, görünən
python3 src/firefox_bot.py https://turanly.com

# iPhone kimi (mobil emulyasiya)
python3 src/firefox_bot.py https://turanly.com --mobile

# bir neçə dəfə + gizli
python3 src/firefox_bot.py https://turanly.com --visits 3 --headless
```

---

## 2) iPhone Safari bot (REAL cihaz)

### Tələblər
- Xcode + Command Line Tools
- Node 22+, Appium 3.x, `xcuitest` driver
- Python: `pip3 install --user Appium-Python-Client`
- iPhone-da **Developer Mode** açıq
- Xcode-a Apple ID əlavə olunub (Team ID `src/iphone_safari_bot.py` içində)

### İşə salma ardıcıllığı
```bash
# Terminal A — tunnel (iOS 17+ üçün, sudo parol istəyir), açıq saxla
./scripts/start_tunnel.sh

# Terminal B — Appium server, açıq saxla
./scripts/start_appium.sh

# Terminal C — botu işə sal
python3 src/iphone_safari_bot.py https://turanly.com
```

İlk işə salışda WebDriverAgent telefona qurulur; telefonda
**Settings → General → VPN & Device Management** bölməsindən developer-i **Trust**
etmək lazım ola bilər. Telefon kiliddi açıq olsun.

---

## 3) Android Chrome bot (REAL cihaz)

iOS-dan **xeyli sadədir**: sudo yoxdur, tunnel yoxdur, Apple Team ID yoxdur,
**Appium server də yoxdur.** Yalnız `adb` + `chromedriver`.

### Nə üçün Appium deyil

Xiaomi/MIUI (və HyperOS) `adb install`-u bloklayır:

```
INSTALL_FAILED_USER_RESTRICTED: Install canceled by user
```

Bunu açmaq üçün **"Install via USB"** toggle-ı lazımdır, o isə Mi hesabı + SIM
+ bəzən 24 saat gözləmə tələb edir. Appium telefona öz köməkçi APK-larını
(`io.appium.settings`, `io.appium.uiautomator2.server`) qura bilmədiyi üçün işə düşmür.

`chromedriver` isə telefondakı Chrome-a **adb üzərindən birbaşa** qoşulur —
heç nə qurulmur, bu qadağa ona təsir etmir.

### Tələblər
- Android SDK platform-tools (`adb`) — var: `~/Library/Android/sdk`
- Python: `selenium` — var (`/usr/bin/python3`)
- Telefonda **Developer options** aç:
  Settings → About phone → **"OS version"**-a 7 dəfə toxun
  *(Xiaomi-də "Build number" yoxdur — "OS version"-dur)*
- **Developer options → USB debugging** aç
- Bildiriş panelindən USB rejimini **File Transfer** seç
  *(yalnız "Charging" olsa `adb` cihazı görmür)*
- Telefonda çıxan **"Allow USB debugging?"** → **Always allow** → **Allow**

### Cihazın görünməsini yoxla
```bash
source scripts/env.sh
adb devices -l     # "device" statusunda görünməlidir
```

Görünmürsə USB Product ID-yə bax — `0xff40` = yalnız MTP (debugging bağlıdır),
`0xff48` = MTP + ADB (düzgün):
```bash
system_profiler SPUSBDataType | grep -A4 -i redmi
```

### İşə salmaq
```bash
source scripts/env.sh
$PY src/android_chrome_bot.py https://turanly.com
```

### Parametrlər
```bash
--visits 3     # neçə dəfə girsin
--js           # real toxunuş əvəzinə JS scroll (window.scrollBy)
--udid XXXX    # bir neçə cihaz varsa hansını seçsin
```

**Scroll rejimi:** default olaraq `adb shell input swipe` — bu, OS səviyyəsində
**əsl barmaq toxunuşudur**, səhifə real touch event-ləri görür. `--js` isə
`window.scrollBy` işlədir: daha dəqiqdir, amma toxunuş hadisəsi yaratmır.

chromedriver-i Selenium Manager telefondakı Chrome versiyasına uyğun özü tapır/yükləyir.

### Test nəticəsi (Redmi 15C, Android 15, Chrome 150)
```
Cihaz: 25078RA3EY | Android 15 | ekran 720x1600 | Chrome 150.0.7871.186
  -> Basliq: Turan Hidayatov | Full-Stack Web Developer
  -> URL:    https://turanly.com/az
  -> Movqe: 3069px / 4122px
Bitdi: 1/1 ugurlu ✅
```
