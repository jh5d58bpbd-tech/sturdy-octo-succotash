#!/usr/bin/env python3
"""計算結果(.result.json) を 見積サンプル と同じデザインの HTML / PDF にする。

使い方:
  python3 tools/render.py 見積書/xxx.result.json      → xxx.html と xxx.pdf を出力
"""
import base64
import html
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROWS_MIN = 16  # 明細欄の最低行数（サンプルは16行で以下余白＋空欄）


def e(s):
    return html.escape(str(s if s is not None else ""))


def num(v):
    return "" if v is None or v == "" else f"{int(v):,}"


def wareki_free(d):
    y, m, dd = d.split("-")
    return f'{int(y)} <b>年</b> {int(m)} <b>月</b> {int(dd)} <b>日</b>'


def render(res):
    co = json.loads((ROOT / "data" / "company.json").read_text(encoding="utf-8"))
    seal = ""
    if co.get("角印") and (ROOT / co["角印"]).exists():
        b64 = base64.b64encode((ROOT / co["角印"]).read_bytes()).decode()
        seal = f'<img class="seal" src="data:image/png;base64,{b64}">'

    rows = []
    for l in res["明細"]:
        k = l.get("種別", "明細")
        if k == "見出し":
            rows.append(f'<tr><td class="name">{e(l["品名"])}</td><td></td><td></td><td></td><td></td></tr>')
        elif k == "注記":
            rows.append(f'<tr><td class="name note" colspan="5"><span>{e(l["品名"])}</span></td></tr>')
        elif k == "空行":
            rows.append('<tr><td></td><td></td><td></td><td></td><td></td></tr>')
        else:
            rows.append(
                f'<tr><td class="name">{e(l["品名"])}<small>{e(l.get("規格"))}</small></td>'
                f'<td class="r b">{e(l.get("数量"))}</td><td class="c b">{e(l.get("単位"))}</td>'
                f'<td class="r b">{num(l.get("単価"))}</td><td class="r b">{num(l.get("金額"))}</td></tr>')
    rows.append('<tr><td class="name yohaku">以下余白</td><td></td><td></td><td></td><td></td></tr>')
    while len(rows) < ROWS_MIN:
        rows.append('<tr><td></td><td></td><td></td><td></td><td></td></tr>')

    rate = int(round(float(res.get("税率", 0.10)) * 100))
    honorific = res.get("敬称", "様")
    to_lines = [res.get("宛先", "")] + ([f'{res["宛先担当"]} {honorific}'] if res.get("宛先担当") else [])
    if not res.get("宛先担当"):
        to_lines[0] += f" {res.get('敬称', '御中')}"
    terms = [("納入期日", res.get("納入期日", "")), ("受渡場所", res.get("受渡場所", "")),
             ("取引方法", res.get("取引方法", "")), ("有効期限", res.get("有効期限", ""))]

    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>{e(res.get('件名','御見積書'))}</title>
<style>
@page {{ size: A4; margin: 0; }}
:root {{ --blue:#0000a0; --head:#c8c8ff; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#fff; font-family:"IPAPGothic","IPAGothic","Hiragino Sans","Yu Gothic",sans-serif; color:#000; }}
.page {{ width:210mm; height:297mm; padding:14mm 12mm 10mm; position:relative; font-size:10.5pt; }}
h1 {{ margin:0 auto; width:68mm; background:var(--blue); color:#fff; text-align:center;
     font-weight:normal; font-size:21pt; letter-spacing:.5em; padding:1mm 0 1mm .5em; }}
.blue {{ color:var(--blue); }}
.top {{ display:flex; justify-content:space-between; margin-top:3mm; }}
.left {{ width:88mm; }}
.docno {{ font-size:9.5pt; }}
.to {{ font-size:13pt; margin-top:4mm; line-height:1.35; border-bottom:1px solid #000; padding-bottom:1mm; }}
.subject {{ font-size:11.5pt; margin-top:4mm; border-bottom:1px solid var(--blue); padding:0 0 1mm; }}
.lead {{ text-align:center; margin-top:4mm; }}
.terms {{ margin-top:5mm; line-height:1.75; font-size:10pt; }}
.terms span.k {{ display:inline-block; width:28mm; text-align-last:justify; padding-right:6mm; }}
.right {{ width:84mm; position:relative; }}
.date {{ text-align:right; font-size:11.5pt; margin-top:1mm; }}
.date b {{ font-weight:normal; color:var(--blue); }}
.co {{ margin-top:7mm; font-size:9.5pt; line-height:1.3; position:relative; }}
.co .nm {{ font-size:13pt; }}
.seal {{ position:absolute; left:34mm; top:-2mm; width:20mm; opacity:.9; }}
.stamps {{ display:flex; justify-content:flex-end; margin-top:9mm; }}
.stamps div {{ width:19mm; height:19mm; border:1px solid var(--blue); }}
.stamps div + div {{ border-left:none; }}
table {{ border-collapse:collapse; width:100%; }}
.sum {{ margin-top:3mm; border:2px solid var(--blue); }}
.sum th {{ background:var(--head); color:var(--blue); font-weight:normal; font-size:8pt; letter-spacing:.6em;
           border:1px solid var(--blue); height:5mm; }}
.sum td {{ border:1px solid var(--blue); height:11mm; font-size:12pt; padding:0 1.5mm; }}
.sum td.total {{ font-size:15pt; text-align:right; }}
.tax {{ display:flex; justify-content:space-between; }}
.items {{ margin-top:4mm; border:2px solid var(--blue); table-layout:fixed; }}
.items th {{ background:var(--head); color:var(--blue); font-weight:normal; font-size:11pt; letter-spacing:.4em;
             border:1px solid var(--blue); height:9mm; }}
.items td {{ border-left:1px solid var(--blue); border-right:1px solid var(--blue); border-top:1px solid var(--blue);
             height:9.3mm; vertical-align:bottom; padding:0 1.5mm 1mm; font-size:10.5pt; }}
.items td.name {{ vertical-align:top; padding-top:1mm; line-height:1.25; }}
.items td.name small {{ display:block; font-size:7.5pt; }}
.items td.note {{ border-right:none; }}
.items td.note span {{ white-space:nowrap; }}
.items td.yohaku {{ padding-left:30mm; }}
.r {{ text-align:right; }} .c {{ text-align:center; }}
</style></head><body><div class="page">
<h1>御見積書</h1>
<div class="top">
 <div class="left">
  <div class="docno blue">書類No. {e(res.get('書類No',''))}</div>
  <div class="to">{'<br>'.join(e(x) for x in to_lines)}</div>
  <div class="subject">{e(res.get('件名',''))}</div>
  <div class="lead blue">下記のとおり御見積り申し上げます。</div>
  <div class="terms blue">{''.join(f'<div><span class="k">{k}</span><span style="color:#000">{e(v)}</span></div>' for k, v in terms)}</div>
 </div>
 <div class="right">
  <div class="date">{wareki_free(res.get('日付', date.today().isoformat()))}</div>
  <div class="co">{seal}<div class="nm">{e(co['会社名'])}</div>
   〒{e(co['郵便番号'])} {e(co['住所1'])}<br>{e(co['住所2'])}<br>TEL{e(co['TEL'])}<br>(登録番号 {e(co['登録番号'])})</div>
  <div class="stamps"><div></div><div></div></div>
 </div>
</div>
<table class="sum"><tr><th>小計</th><th>消費税</th><th>合計金額</th></tr>
<tr><td class="r" style="width:33%">￥{num(res['小計'])}</td>
<td style="width:33%"><div class="tax"><span>外税{rate}%</span><span>￥{num(res['消費税'])}</span></div></td>
<td class="total">￥{num(res['合計'])}</td></tr></table>
<table class="items"><colgroup><col style="width:40.5%"><col style="width:16.5%"><col style="width:7.7%"><col style="width:17%"><col></colgroup>
<tr><th>内容・仕様</th><th>数量</th><th>単位</th><th>単価</th><th>金額</th></tr>
{''.join(rows)}
</table>
</div></body></html>"""


def main():
    src = Path(sys.argv[1])
    res = json.loads(src.read_text(encoding="utf-8"))
    stem = src.name.replace(".result.json", "")
    out_html = src.with_name(stem + ".html")
    out_html.write_text(render(res), encoding="utf-8")
    out_pdf = src.with_name(stem + ".pdf")
    subprocess.run(["node", str(ROOT / "tools" / "pdf.js"), str(out_html), str(out_pdf)], check=True)
    print(f"→ {out_html}\n→ {out_pdf}")


if __name__ == "__main__":
    main()
