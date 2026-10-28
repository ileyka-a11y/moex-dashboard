#!/usr/bin/env python3
"""Снимок котировок всех акций Мосбиржи (режим TQBR) для дашборда.

Пишет:
  data/latest.json             — последний снимок
  data/history/YYYY-MM-DD.json — все снимки дня (для графиков истории)
  data/history/index.json      — список месяцев с историей
Без внешних зависимостей: только стандартная библиотека Python.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")
ISS = "https://iss.moex.com/iss"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "moex-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def table(block):
    cols = block["columns"]
    return [dict(zip(cols, row)) for row in block["data"]]


def main():
    base = json.load(open(os.path.join(DATA, "base.json"), encoding="utf-8"))
    tickers = {s["t"] for s in base["stocks"]}

    j = get(
        f"{ISS}/engines/stock/markets/shares/boards/TQBR/securities.json?iss.meta=off"
        "&iss.only=securities,marketdata"
        "&securities.columns=SECID,PREVLEGALCLOSEPRICE,PREVPRICE"
        "&marketdata.columns=SECID,LAST,LCURRENTPRICE,VALTODAY,SYSTIME"
    )
    sec = {r["SECID"]: r for r in table(j["securities"])}
    md = {r["SECID"]: r for r in table(j["marketdata"])}

    prices = {}
    systime = None
    for t in sorted(tickers):
        s, m = sec.get(t, {}), md.get(t, {})
        prev = s.get("PREVLEGALCLOSEPRICE") or s.get("PREVPRICE")
        last = m.get("LAST") or m.get("LCURRENTPRICE")
        val = round((m.get("VALTODAY") or 0) / 1e6, 3)
        prices[t] = [last, prev, val]
        if m.get("SYSTIME"):
            systime = max(systime or "", m["SYSTIME"])

    idx = get(
        f"{ISS}/engines/stock/markets/index/securities/IMOEX.json?iss.meta=off"
        "&iss.only=marketdata&marketdata.columns=SECID,CURRENTVALUE,LASTVALUE,LASTCHANGE"
    )
    imd = table(idx["marketdata"])[0]
    cur = imd.get("CURRENTVALUE")
    prev = (cur - imd["LASTCHANGE"]) if (cur is not None and imd.get("LASTCHANGE") is not None) else imd.get("LASTVALUE")
    imoex = {"last": cur, "prev": round(prev, 2) if prev else None}

    traded = sum(1 for v in prices.values() if v[0] is not None)
    if traded == 0:
        print("Нет ни одной цены — биржа не ответила данными, снимок не сохраняю", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(MSK)
    snap = {
        "time": now.isoformat(timespec="minutes"),
        "exchangeTime": systime,
        "source": "ISS MOEX (задержка ~15 мин)",
        "imoex": imoex,
        "prices": prices,
    }
    json.dump(snap, open(os.path.join(DATA, "latest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    day = now.strftime("%Y-%m-%d")
    hdir = os.path.join(DATA, "history")
    os.makedirs(hdir, exist_ok=True)
    hpath = os.path.join(hdir, f"{day}.json")
    hist = json.load(open(hpath, encoding="utf-8")) if os.path.exists(hpath) else {"times": [], "imoex": [], "px": {}}
    n = len(hist["times"])
    hist["times"].append(snap["time"])
    hist["imoex"].append(imoex["last"])
    for t in sorted(tickers):
        hist["px"].setdefault(t, [None] * n).append(prices[t][0])
    for t, arr in hist["px"].items():  # бумаги, пропавшие из списка
        if len(arr) < n + 1:
            arr.extend([None] * (n + 1 - len(arr)))
    json.dump(hist, open(hpath, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    ipath = os.path.join(hdir, "index.json")
    index = json.load(open(ipath)) if os.path.exists(ipath) else {}
    days = sorted(set(index.get("days", [])) | {day})
    json.dump({"days": days}, open(ipath, "w"))

    print(f"Снимок {snap['time']}: цен {traded} из {len(tickers)}, IMOEX {imoex['last']}")


if __name__ == "__main__":
    main()
