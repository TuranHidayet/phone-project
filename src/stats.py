#!/usr/bin/env python3
"""
Is qeydiyyati ve statistika.

Her is (ugurlu ve ya xetali) logs/runs.jsonl fayllina BIR SETIR olaraq yazilir:
    {"ts": 1765..., "date": "2026-08-09", "serial": "192.168.31.36:5555",
     "model": "25078RA3EY", "android": "15", "query": "...", "status": "ok",
     "secs": 209.4, "url": "azstudy.az", "error": null}

Statistika buradan hesablanir -- log faylini parse etmek yerine struktur
qeyd saxlamaq daha etibarlidir (log formati deyisse statistika pozulmur).

Istifade:
    $PY src/stats.py report --period day          # bugunku hesabat (ekrana)
    $PY src/stats.py report --period day --send   # Telegram-a gonder
    $PY src/stats.py report --period month --send
"""

import os
import io
import json
import time
import argparse
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS_FILE = os.path.join(BASE, "logs", "runs.jsonl")

# Model kodlarini oxunakli ada cevirmek ucun (telefon elave olunduqca genislenir)
# Cihazin satis adi ("REDMI 15C") telefonun ozunden oxunur (device_profile),
# ona gore burada elave xerite saxlamaga ehtiyac yoxdur. Kohne qeydlerde
# yalniz model kodu varsa, oxunakli ad ucun ehtiyat xerite:
MODEL_NAMES = {}


def pretty_model(model, serial=""):
    name = MODEL_NAMES.get(model, model or "naməlum")
    if name != model and model:
        return f"{name} ({model})"
    return name or serial


def record(serial, model, android, query, status, secs, url=None, error=None,
           name=None):
    """Bir isin neticesini yazir. Yazma alinmasa proses DAYANMIR."""
    try:
        os.makedirs(os.path.dirname(RUNS_FILE), exist_ok=True)
        row = {
            "ts": time.time(),
            "date": datetime.date.today().isoformat(),
            "serial": serial,
            "model": model,
            "name": name or model,
            "android": android,
            "query": query,
            "status": status,                 # "ok" / "error"
            "secs": round(float(secs), 1),
            "url": url,
            "error": error,
        }
        with open(RUNS_FILE, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def load(since_ts=None):
    rows = []
    try:
        with io.open(RUNS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if since_ts is None or r.get("ts", 0) >= since_ts:
                    rows.append(r)
    except FileNotFoundError:
        pass
    return rows


def _period_bounds(period, ref=None):
    """(baslangic_ts, bitis_ts, basliq) qaytarir."""
    ref = ref or datetime.datetime.now()
    if period == "day":
        start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + datetime.timedelta(days=1)
        title = f"Günlük hesabat — {start.date().isoformat()}"
    elif period == "month":
        # ayin 1-i sabah baslayirsa (gece hesabati) KECEN ay hesablanir
        first_this = ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if ref.day == 1:
            end = first_this
            start = (first_this - datetime.timedelta(days=1)).replace(day=1)
        else:
            start, end = first_this, first_this + datetime.timedelta(days=32)
            end = end.replace(day=1)
        title = f"Aylıq hesabat — {start.strftime('%Y-%m')}"
    else:
        raise ValueError(period)
    return start.timestamp(), end.timestamp(), title


def build_report(period="day", ref=None):
    start_ts, end_ts, title = _period_bounds(period, ref)
    rows = [r for r in load(start_ts) if r.get("ts", 0) < end_ts]

    if not rows:
        return f"<b>{title}</b>\n\nBu dövrdə heç bir iş qeydə alınmayıb."

    # cihaz -> statistika
    devs = {}
    for r in rows:
        key = r.get("serial") or "?"
        d = devs.setdefault(key, {"model": r.get("name") or r.get("model"),
                                  "ok": 0, "err": 0, "secs": 0.0, "errors": []})
        # Kohne qeydlerde satis adi ("REDMI 15C") yoxdur, yalniz model kodu var.
        # Hemin cihazin YENI qeydinde ad varsa, oxunakli adi gotururuk.
        if r.get("name") and r["name"] != r.get("model"):
            d["model"] = r["name"]
        if r.get("status") == "ok":
            d["ok"] += 1
            d["secs"] += r.get("secs") or 0
        else:
            d["err"] += 1
            e = (r.get("error") or "").strip()
            if e and e not in d["errors"]:
                d["errors"].append(e)

    total_ok = sum(d["ok"] for d in devs.values())
    total_err = sum(d["err"] for d in devs.values())
    total_secs = sum(d["secs"] for d in devs.values())

    lines = [f"<b>{title}</b>", ""]
    for serial, d in sorted(devs.items(), key=lambda kv: -kv[1]["ok"]):
        avg = (d["secs"] / d["ok"]) if d["ok"] else 0
        lines.append(f"📱 <b>{pretty_model(d['model'], serial)}</b>")
        lines.append(f"    ✅ tamamlanan: <b>{d['ok']}</b>   ❌ xəta: {d['err']}")
        if d["ok"]:
            lines.append(f"    ⏱ orta müddət: {avg:.0f} san   "
                         f"cəmi: {d['secs'] / 60:.0f} dəq")
        for e in d["errors"][:3]:
            lines.append(f"    ⚠️ {e[:120]}")
        lines.append("")

    if len(devs) > 1:
        lines.append("━━━━━━━━━━━━━━")
        lines.append(f"<b>ÜMUMİ ({len(devs)} cihaz)</b>")
        lines.append(f"✅ tamamlanan: <b>{total_ok}</b>   ❌ xəta: {total_err}")
        lines.append(f"⏱ cəmi iş vaxtı: {total_secs / 60:.0f} dəq")
    else:
        lines.append(f"⏱ cəmi iş vaxtı: {total_secs / 60:.0f} dəq")

    return "\n".join(lines).strip()


def main():
    p = argparse.ArgumentParser(description="AzStudy bot statistikasi")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("report", help="Hesabat qur")
    r.add_argument("--period", choices=["day", "month"], default="day")
    r.add_argument("--send", action="store_true", help="Telegram-a gonder")

    args = p.parse_args()
    if args.cmd == "report":
        text = build_report(args.period)
        if args.send:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import notify
            ok = notify.send(text)
            print("gonderildi" if ok else "GONDERILMEDI (Telegram qurasdirilmayib?)")
            print(text.replace("<b>", "").replace("</b>", ""))
        else:
            print(text.replace("<b>", "").replace("</b>", ""))


if __name__ == "__main__":
    main()
