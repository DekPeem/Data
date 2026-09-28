# DBD DataWarehouse scraper

> **Note for this copy.** The standalone CLI (`main.py`) and the helpers
> only it used are not included — SolarFit drives the scraper through
> `../pull.py` instead, so the `Use` section below describes the original
> in `pull_amr_data/dbd_scrape/`, not this copy. Every module documented
> in the file table is here and unchanged.

Pulls a company's ข้อมูลนิติบุคคล and one financial statement from
<https://datawarehouse.dbd.go.th/> with Playwright, and writes both to CSV.

The flow it drives is the one a person would follow:

1. type the 13-digit registration id into the home search box and submit
2. read the ข้อมูลนิติบุคคล card
3. open the **ข้อมูลงบการเงิน** tab › **งบการเงิน**
4. pick the fiscal year in **เลือกปีงบการเงิน** (Buddhist era, e.g. 2568)
5. click each statement and read its table — by default all three
   (**งบกำไรขาดทุน**, **งบแสดงฐานะการเงิน**, **อัตราส่วนทางการเงิน**), in the
   same visit

No login is needed; the site is public.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

## Use

```bash
.venv/bin/python main.py fetch                                  # 0105532096634, 2568, all 3 statements
.venv/bin/python main.py fetch --id 0105532096634 --year 2568
.venv/bin/python main.py fetch --statement งบแสดงฐานะการเงิน       # just the balance sheet
.venv/bin/python main.py fetch --statement อัตราส่วนทางการเงิน --long
.venv/bin/python main.py fetch --ids 0105532096634,0105536000123 --out ./out
```

| flag | meaning |
| --- | --- |
| `--id` / `--ids` | one registration id, or a comma-separated list |
| `--year` | fiscal year, Buddhist era (default 2568) |
| `--statement` | one or more of งบกำไรขาดทุน, งบแสดงฐานะการเงิน, อัตราส่วนทางการเงิน (default: all three) |
| `--long` | write one row per (year, line item) instead of the on-screen shape |
| `--out` | output directory (default `output/`) |
| `--headless` | run without a browser window (needs Google Chrome — see below) |

## Output

`output/juristic_<id>.csv` — one row per company, one column per field, so
repeated runs concatenate cleanly:

```
เลขทะเบียนนิติบุคคล,ชื่อนิติบุคคล,ประเภทนิติบุคคล,สถานะนิติบุคคล,วันที่จดทะเบียนจัดตั้ง,ทุนจดทะเบียน,…
0105532096634,บริษัท ทิปโก้ เอฟแอนด์บี จำกัด,บริษัทจำกัด,ยังดำเนินกิจการอยู่,10 ต.ค. 2532,"700,000,000.00 บาท",…
```

`output/income_statement_<id>_<year>.csv` — the statement as displayed, one row
per line item and two columns per fiscal year:

```
หน่วย : บาท,2564 จำนวนเงิน,2564 %เปลี่ยนแปลง,…,2568 จำนวนเงิน,2568 %เปลี่ยนแปลง
รายได้หลัก,1516726798.00,-6.33,…,1758960377.00,-2.51
```

`output/balance_sheet_<id>_<year>.csv` — same shape as the income statement:
the summary lines the site shows (not a full chart of accounts), two columns per
fiscal year.

```
หน่วย : บาท,2564 จำนวนเงิน,2564 %เปลี่ยนแปลง,…,2568 จำนวนเงิน,2568 %เปลี่ยนแปลง
สินทรัพย์รวม,1190949216.00,-11.62,…,1092359058.00,-0.80
หนี้สินรวม,690247475.00,-12.03,…,1043221641.00,-1.72
```

`output/financial_ratio_<id>_<year>.csv` — the 15 key ratios, numbered as on the
site, one column per fiscal year (no %เปลี่ยนแปลง columns for this one):

```
ลำดับที่,อัตราส่วน,2564,2565,2566,2567,2568
1,อัตราผลตอบแทนจากสินทรัพย์รวม (ROA) (%),-4.90,-15.93,-8.13,-16.16,-8.20
```

With `--long`, the same data as `…_long.csv`, one row per (year, line item) —
the shape most downstream joins want. Statements without sub-columns get a
single `ค่า` column instead of จำนวนเงิน / %เปลี่ยนแปลง:

```
เลขทะเบียนนิติบุคคล,งบการเงิน,ปีงบการเงิน,รายการ,จำนวนเงิน,%เปลี่ยนแปลง
0105532096634,งบกำไรขาดทุน,2564,รายได้หลัก,1516726798.00,-6.33
```

Note that the site shows **five years at once**, so `--year` selects which
five-year window you get (2568 → 2564-2568), not a single year.

Numbers are written without thousands separators. A `-` on the site means "not
reported" and becomes an empty cell, never a `0` — those are different claims.
Files are UTF-8 **with BOM** so Excel on Windows renders Thai correctly.

## Things worth knowing

**Headless needs Google Chrome.** The site sits behind Imperva. Tested against
the live site:

| launch | result |
| --- | --- |
| bundled Chromium, headless | `403` bot-block page |
| bundled Chromium, `--headless=new` | `403` bot-block page |
| bundled Chromium, headed | works |
| Google Chrome, `--headless=new` + desktop UA + `STEALTH_JS` | works |

So `--headless` launches the `chrome` channel with those patches (see
`config.py`), which needs Google Chrome installed locally; without it the run
warns and falls back to bundled Chromium, which will be blocked. The default is
headed, since that works with the bundled Chromium alone.

On a headless Linux box with no Chrome, run headed under `xvfb-run` instead.

**Search by id, not by name.** The autocomplete dropdown (`#suggestionContent`)
never opens for typed input under automation, and pressing Enter only navigates
for an exact 13-digit id. The code tries the suggestion list first and falls
back to submitting; a non-id query fails with an explicit message rather than
guessing.

**When something breaks**, a screenshot and the rendered DOM are written to
`debug/`, and the run continues to the next id. Selectors all live in
`config.py` as candidate lists tried in order — start there.

## Layout

| file | role |
| --- | --- |
| `scraper.py` | the site flow: search → juristic card → year → statement → table |
| `report.py` | CSV writers (wide and long) |
| `browser_utils.py` | selector/text helpers and debug dumps |
| `config.py` | URLs, selectors, Thai labels, timeouts |
| `html_source/` | saved markup the selectors were written against |
