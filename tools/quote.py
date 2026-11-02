#!/usr/bin/env python3
"""単価マスタ検索と見積計算。

使い方:
  python3 tools/quote.py search <キーワード...>   品名・規格・コード・カテゴリを検索
  python3 tools/quote.py check                    マスタの重複・欠損チェック
  python3 tools/quote.py calc <明細.json>         見積計算
  python3 tools/quote.py genka <キーワード...>    メーカー定価と仕入値（卸値・掛率）を検索

明細 JSON の例:
{
  "宛先": "株式会社サンプル",
  "件名": "〇〇工事",
  "税率": 0.10,
  "明細": [
    {"コード": "A-001", "数量": 3},
    {"コード": "A-002", "数量": 1, "単価": 5000},
    {"品名": "出張費", "数量": 1, "単位": "式", "単価": 8000},
    {"品名": "値引", "数量": 1, "単位": "式", "単価": -3000},
    {"品番": "PX-570", "数量": 353},   ← カタログ品番: 仕入/㎡＋手間2,000→100円切上げで単価自動（"手間" で上書き可）
    {"見出し": "2.〇〇工事"}, {"注記": "※注意書き"}, {"空行": true}
  ],
  "端数調整単位": 10000
}
行の種類: 明細（コード or 品名）/ {"見出し": ..} / {"注記": ..} / {"空行": true}
"端数調整単位" を書くと小計をその単位で切り捨て、差額を「端数調整」行で入れる。
コード指定の行はマスタから品名・単位・単価を引く。"単価" を書けばそれで上書き。
"""
import csv
import json
import sys
from decimal import Decimal, ROUND_DOWN, ROUND_CEILING
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "prices.csv"
TEMA_M2 = Decimal(2000)      # 床シート材工の手間（円/㎡）ユーザー指定
ROUND_UP = Decimal(100)      # 材工単価の切り上げ単位（円）
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
    lines, subtotal, errors, n = [], Decimal(0), [], 0
    for item in spec["明細"]:
        # 金額を持たない行（見出し・注記・空行）
        if "見出し" in item:
            lines.append({"種別": "見出し", "品名": item["見出し"]}); continue
        if "注記" in item:
            lines.append({"種別": "注記", "品名": item["注記"]}); continue
        if item.get("空行"):
            lines.append({"種別": "空行"}); continue
        n += 1
        if item.get("品番"):
            # カタログ品番から材工単価を自動計算: 仕入(定価×掛率)/㎡ + 手間 → 100円切り上げ
            info = material_price(item["品番"], item.get("手間"))
            if not info:
                errors.append(f"{n}行目: 品番 {item['品番']} の㎡単価・掛率が見つかりません")
                m = {}
            else:
                m = {"品名": "長尺シート張り", "規格": info["規格"], "単位": "㎡", "単価": info["単価"]}
                print(f"   [{item['品番']}] 定価{info['定価']:,}×{info['掛率']}%={info['仕入']:,.1f} + 手間{info['手間']:,} "
                      f"= {info['計算値']:,.1f} → {info['単価']:,}円/㎡")
        else:
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
            "種別": "明細",
            "コード": item.get("コード", ""),
            "品名": item.get("品名", m.get("品名", "")),
            "規格": item.get("規格", m.get("規格", "")),
            "数量": format(qty.normalize(), "f"),
            "単位": item.get("単位", m.get("単位", "")),
            "単価": int(price),
            "金額": int(amount),
        })
    # 端数調整: 小計を指定単位で切り捨てて差額を「端数調整」行にする
    unit = spec.get("端数調整単位")
    if unit:
        rounded = (subtotal // Decimal(unit)) * Decimal(unit)
        diff = rounded - subtotal
        if diff:
            lines.append({"種別": "明細", "品名": "端数調整", "規格": "", "数量": "", "単位": "",
                          "単価": None, "金額": int(diff)})
            subtotal = rounded
    tax = yen(subtotal * rate)
    total = subtotal + tax
    result = {**{k: v for k, v in spec.items() if k != "明細"},
              "明細": lines, "小計": int(subtotal), "消費税": int(tax), "合計": int(total)}

    for l in lines:
        if l["種別"] == "明細":
            q = f"{l['数量']}{l['単位']} × {fmt(l['単価'])} = " if l["単価"] is not None else ""
            print(f"   {l['品名']} {l['規格']}  {q}{fmt(l['金額'])}")
        elif l["種別"] != "空行":
            print(f"■ {l['品名']}")
    print(f"小計 {fmt(subtotal)} / 消費税({rate*100:.0f}%) {fmt(tax)} / 合計 {fmt(total)} 円")
    for e in errors:
        print("警告:", e, file=sys.stderr)

    out = Path(path).with_suffix(".result.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {out}")
    return out


def _read(name):
    p = ROOT / "data" / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def ceil_to(v, unit=ROUND_UP):
    return int((Decimal(v) / unit).to_integral_value(rounding=ROUND_CEILING) * unit)


def material_price(code, tema=None):
    """品番(例 PX-570) の ㎡ 行から 仕入値と材工単価を求める"""
    by_id = {r["ID"]: r for r in _read("shiire.csv")}
    for r in _read("catalog.csv"):
        if r["品番"] == code and r["単位"] == "㎡":
            ref = by_id.get(r.get("仕入掛率ID", ""))
            if not ref or ref.get("掛率") in ("", "0"):
                return None
            cost = Decimal(r["定価"]) * Decimal(ref["掛率"]) / 100
            t = Decimal(str(tema)) if tema is not None else TEMA_M2
            return {"定価": int(r["定価"]), "掛率": ref["掛率"], "仕入": cost, "手間": int(t),
                    "計算値": cost + t, "単価": ceil_to(cost + t),
                    "規格": f"{r['メーカー']} {r['シリーズ']} {code} {r['厚み']}"}
    return None


def cmd_genka(words):
    words = [w.lower() for w in words]
    shiire = _read("shiire.csv")
    by_id = {r["ID"]: r for r in shiire}
    match = lambda r, cols: all(w in " ".join(r.get(c, "") or "" for c in cols).lower() for w in words)
    print("【メーカー定価（カタログ）→ 仕入値】")
    n = 0
    for r in _read("catalog.csv"):
        if not match(r, ("メーカー", "シリーズ", "品番", "品名")):
            continue
        n += 1
        ref = by_id.get(r.get("仕入掛率ID", ""))
        cost = ""
        if ref and ref.get("掛率") not in ("", "0"):
            cost = f" × {ref['掛率']}% = 仕入 {Decimal(r['定価']) * Decimal(ref['掛率']) / 100:,.1f}円"
            if r["単位"] == "㎡":
                v = Decimal(r["定価"]) * Decimal(ref["掛率"]) / 100 + TEMA_M2
                cost += f" ＋手間{int(TEMA_M2):,} = 材工{v:,.1f} → 見積単価 {ceil_to(v):,}円/㎡"
        elif not ref:
            cost = " （掛率未登録）"
        print(f"{r['メーカー']} {r['シリーズ']} {r['品番']} {r['厚み']}  定価 {int(r['定価']):,}円/{r['単位']}{cost}"
              + (f"  ※{r['備考']}" if r.get("備考") else ""))
    print("【仕入表（卸値・掛率）】")
    for r in shiire:
        if not match(r, ("メーカー", "カテゴリ", "品名", "規格")):
            continue
        n += 1
        v = f"{int(r['仕入単価']):,}円/{r['単位']}" if r["仕入単価"] not in ("",) else (f"掛率 {r['掛率']}%" if r["掛率"] else "-")
        j = f" 上代{int(r['上代']):,}円" if r.get("上代") else ""
        print(f"{r['ID']} {r['メーカー']} {r['品名']} {r['規格']}  {v}{j}  [{r['仕入先']} {r['適用日']}~]"
              + (f"  ※{r['備考']}" if r.get("備考") else ""))
    print(f"-- {n} 件", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "search":
        cmd_search(args)
    elif cmd == "genka":
        cmd_genka(args)
    elif cmd == "check":
        cmd_check()
    elif cmd == "calc" and args:
        cmd_calc(args[0])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
