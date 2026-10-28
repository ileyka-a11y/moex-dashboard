#!/usr/bin/env python3
"""Обновляет дивиденды в data/base.json по таблицам smart-lab.ru/dividends.

Берёт таблицы за прошлый, текущий и следующий год. Если сайт недоступен или
формат изменился — оставляет прежние данные и завершается без ошибки.
"""
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BASE = os.path.join(ROOT, "data", "base.json")


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.row, self.cell, self.depth = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.tables.append([])
        elif tag == "tr" and self.depth == 1:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.depth -= 1
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.depth == 1:
            self.tables[-1].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def fetch(year):
    url = f"https://smart-lab.ru/dividends/index?year={year}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (moex-dashboard)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    p = Tables()
    p.feed(html)
    for t in p.tables:
        if t and t[0] and t[0][0].startswith("Название") and "Тикер" in t[0]:
            h = t[0]
            it, iv, idt = h.index("Тикер"), h.index("Дивиденд,руб"), h.index("Дата закрытия реестра")
            out = []
            for r in t[1:]:
                if len(r) <= max(it, iv, idt):
                    continue
                d, v = r[idt], r[iv].replace(",", ".").replace(" ", "")
                try:
                    dd = date(int(d[6:10]), int(d[3:5]), int(d[0:2]))
                    out.append((r[it], dd, float(v)))
                except (ValueError, IndexError):
                    continue
            return out
    raise ValueError("таблица дивидендов не найдена")


def main():
    today = date.today()
    rows = []
    try:
        for y in (today.year - 2, today.year - 1, today.year, today.year + 1):
            try:
                rows += fetch(y)
            except ValueError:
                pass
    except Exception as e:  # сеть, блокировка и т.п.
        print(f"smart-lab недоступен ({e}) — дивиденды не обновлены", file=sys.stderr)
        return
    if len(rows) < 50:
        print(f"Слишком мало строк ({len(rows)}) — дивиденды не обновлены", file=sys.stderr)
        return

    by = {}
    for t, d, v in set(rows):
        by.setdefault(t, []).append((d, v))
    base = json.load(open(BASE, encoding="utf-8"))
    year_ago = today - timedelta(days=365)
    n = 0
    for s in base["stocks"]:
        lst = sorted(by.get(s["t"], []))
        if not lst:
            s["div"] = None
            continue
        past = [x for x in lst if x[0] <= today]
        fut = [x for x in lst if x[0] > today]
        s["div"] = {
            "last": [past[-1][0].isoformat(), past[-1][1]] if past else None,
            "next": [fut[0][0].isoformat(), fut[0][1]] if fut else None,
            "months": sorted({x[0].month for x in lst}),
            "sum12": round(sum(v for d, v in past if d > year_ago), 6),
        }
        n += 1
    base["divUpdated"] = today.isoformat()
    json.dump(base, open(BASE, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"Дивиденды обновлены: {n} бумаг, строк {len(rows)}")


if __name__ == "__main__":
    main()
