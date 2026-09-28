"""CSV writers for the scraped juristic data and financial statements."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from . import config
from .scraper import to_number

# ASCII stems, so the filenames stay shell- and Windows-friendly.
STATEMENT_SLUG = {
    config.STATEMENT_INCOME: "income_statement",
    config.STATEMENT_BALANCE: "balance_sheet",
    config.STATEMENT_RATIO: "financial_ratio",
}


def _open(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Excel on Windows reads Thai as mojibake without the BOM.
    return path.open("w", newline="", encoding="utf-8-sig")


def write_juristic(data: dict[str, str], company_id: str, out_dir: Path) -> Path:
    """One row per company, one column per field — so runs concatenate cleanly."""
    path = out_dir / f"juristic_{company_id}.csv"
    with _open(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(data))
        writer.writeheader()
        writer.writerow(data)
    return path


def write_financial(
    table: dict[str, Any],
    company_id: str,
    year: str,
    statement: str,
    out_dir: Path,
    *,
    long_format: bool = False,
) -> Path:
    """Write the statement table, mirroring the site's layout by default.

    Wide (default) keeps the on-screen shape — one row per line item, two
    columns per fiscal year. `long_format` emits one row per (year, item)
    instead, which is the shape most downstream joins want.
    """
    slug = STATEMENT_SLUG.get(statement, "statement")
    suffix = "_long" if long_format else ""
    path = out_dir / f"{slug}_{company_id}_{year}{suffix}.csv"

    with _open(path) as handle:
        writer = csv.writer(handle)
        if long_format:
            _write_long(writer, table, company_id, statement)
        else:
            _write_wide(writer, table)
    return path


def _column_label(column: dict[str, str]) -> str:
    return " ".join(part for part in (column["group"], column["sub"]) if part)


def _write_wide(writer, table: dict[str, Any]) -> None:
    label_headers = table["labelHeaders"] or ["รายการ"]
    writer.writerow(label_headers + [_column_label(c) for c in table["columns"]])

    for row in table["rows"]:
        writer.writerow(row["labels"] + [to_number(v) for v in row["values"]])


def _write_long(writer, table: dict[str, Any], company_id: str, statement: str) -> None:
    """Pivot to one row per (fiscal year, line item).

    Columns are grouped by year in source order, so grouping the flat column
    list by `group` recovers each year's sub-columns (จำนวนเงิน / %เปลี่ยนแปลง).
    Statements without sub-columns (อัตราส่วนทางการเงิน) get a single ค่า column.
    """
    subs: list[str] = []
    for column in table["columns"]:
        if column["sub"] and column["sub"] not in subs:
            subs.append(column["sub"])

    writer.writerow(
        ["เลขทะเบียนนิติบุคคล", "งบการเงิน", "ปีงบการเงิน", "รายการ"] + (subs or ["ค่า"])
    )

    for row in table["rows"]:
        # The rightmost label column is the line item; anything left of it is a
        # row number (อัตราส่วนทางการเงิน's ลำดับที่), which the long shape drops.
        item = next((label for label in reversed(row["labels"]) if label), "")
        if not row["values"]:
            continue  # a section heading row — no figures to pivot

        by_year: dict[str, dict[str, str]] = {}
        order: list[str] = []
        for column, value in zip(table["columns"], row["values"]):
            year = column["group"]
            if year not in by_year:
                by_year[year] = {}
                order.append(year)
            by_year[year][column["sub"] or "ค่า"] = to_number(value)

        for year in order:
            cells = by_year[year]
            writer.writerow(
                [company_id, statement, year, item]
                + [cells.get(sub, "") for sub in (subs or ["ค่า"])]
            )
