#!/usr/bin/env python3
"""単価マスタ検索と見積計算。

使い方:
  python3 tools/quote.py search <キーワード...>   品名・規格・コード・カテゴリを検索
  python3 tools/quote.py check                    マスタの重複・欠損チェック
  python3 tools/quote.py calc <明細.json>         見積計算

明細 JSON の例:
{
  "宛先": "株式会社サンプル",
  "件名": "〇〇工事",
  "税率": 0.10,
  "明細": [
    {"コード": "A-001", "数量": 3},
    {"コード": "A-002", "数量": 1, "単価": 5000},
    {"品名": "出張費", "数量": 1, "単位": "式", "単価": 8000},
    {"品名": "値引", "数量": 1, "単位": "式", "単価": -3000}
  ]
}
コード指定の行はマスタから品名・単位・単価を引く。"単価" を書けばそれで上書き。
"""
import csv
import json
import sys
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "prices.csv"
COLUMNS = ["コード", "品名", "規格", "単位", "単価", "カテゴリ", "出典", "備考"]


def load_prices():
    if not PRICES.exists():
        return []
    with PRICES.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def yen(d):
    return d.quantize(Decimal("1"), rounding=ROUND_DOWN)


def fmt(d):
    return f"{int(d):,}"


def cmd_search(words):
    rows = load_prices()
    words = [w.lower() for w in words]
    hits = [r for r in rows
            if all(w in " ".join(r.get(c, "") or "" for c in ("コード", "品名", "規格", "カテゴリ")).lower()
                   for w in words)]
    for r in hits:
        print(f"{r['コード']}\t{r['品名']}\t{r.get('規格','')}\t{r['単価']}円/{r.get('単位','')}\t[{r.get('出典','')}]"
              + (f"\t※{r['備考']}" if r.get("備考") else ""))
    print(f"-- {len(hits)} 件", file=sys.stderr)


def cmd_check():
    rows = load_prices()
    seen, problems = {}, []
    for i, r in enumerate(rows, start=2):
        code = (r.get("コード") or "").strip()
        if not code:
            problems.append(f"{i}行目: コードなし")
        elif code in seen:
            problems.append(f"{i}行目: コード重複 {code}（{seen[code]}行目）")
        else:
            seen[code] = i
        try:
            Decimal(str(r.get("単価", "")).replace(",", ""))
        except Exception:
            problems.append(f"{i}行目: 単価が数値でない '{r.get('単価')}'")
        if "要確認" in (r.get("備考") or ""):
            problems.append(f"{i}行目: 要確認 {code} {r.get('品名')}")
    print(f"{len(rows)} 品目")
    print("\n".join(problems) or "問題なし")


def cmd_calc(path):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    master = {r["コード"]: r for r in load_prices()}
    rate = Decimal(str(spec.get("税率", "0.10")))
    lines, subtotal, errors = [], Decimal(0), []
    for n, item in enumerate(spec["明細"], start=1):
        m = master.get(item.get("コード", ""), {})
        if item.get("コード") and not m:
            errors.append(f"{n}行目: コード {item['コード']} がマスタにありません")
        price = item.get("単価", m.get("単価"))
        if price in (None, ""):
            errors.append(f"{n}行目: 単価不明")
            price = 0
        price = Decimal(str(price).replace(",", ""))
        qty = Decimal(str(item.get("数量", 1)))
        amount = yen(price * qty)
        subtotal += amount
        lines.append({
            "No": n,
            "コード": item.get("コード", ""),
            "品名": item.get("品名", m.get("品名", "")),
            "規格": item.get("規格", m.get("規格", "")),
            "数量": str(qty.normalize()),
            "単位": item.get("単位", m.get("単位", "")),
            "単価": int(price),
            "金額": int(amount),
        })
    tax = yen(subtotal * rate)
    total = subtotal + tax
    result = {**{k: v for k, v in spec.items() if k != "明細"},
              "明細": lines, "小計": int(subtotal), "消費税": int(tax), "合計": int(total)}

    for l in lines:
        print(f"{l['No']:>2} {l['品名']} {l['規格']}  {l['数量']}{l['単位']} × {fmt(l['単価'])} = {fmt(l['金額'])}")
    print(f"小計 {fmt(subtotal)} / 消費税({rate*100:.0f}%) {fmt(tax)} / 合計 {fmt(total)} 円")
    for e in errors:
        print("警告:", e, file=sys.stderr)

    out = Path(path).with_suffix(".result.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {out}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "search":
        cmd_search(args)
    elif cmd == "check":
        cmd_check()
    elif cmd == "calc" and args:
        cmd_calc(args[0])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
