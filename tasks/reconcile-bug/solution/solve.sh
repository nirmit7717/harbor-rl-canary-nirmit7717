#!/bin/bash
# Reference fix for /app/reconcile.py:
#   1. CLI expects exactly one argument (len(sys.argv) == 2).
#   2. Only VALID rows count as valid; PENDING counts toward nothing.
#   3. Duplicates keep the latest actual instant, not the largest timestamp string.
# Robustness behaviour (BOM, malformed rows, Decimal-exact output, no negative
# zero) is already present in the shipped file and is kept unchanged.
set -euo pipefail

cat > /app/reconcile.py <<'PY'
#!/usr/bin/env python3
"""Summarise a transaction CSV (tx_id,timestamp,amount,status) as JSON."""

import csv
import sys
from datetime import datetime
from decimal import MAX_PREC, ROUND_HALF_UP, Decimal, DecimalException, localcontext
from pathlib import Path

REQUIRED_COLUMNS = ("tx_id", "timestamp", "amount", "status")
KNOWN_STATUSES = {"VALID", "FAILED", "PENDING"}


def parse_timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a UTC offset: {value!r}")
    return parsed


def parse_amount(value):
    try:
        amount = Decimal(value)
    except DecimalException:
        raise ValueError(f"Invalid amount: {value!r}") from None
    if not amount.is_finite():
        raise ValueError(f"Amount must be finite: {value!r}")
    return amount


def reconcile(csv_path):
    latest = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not set(REQUIRED_COLUMNS).issubset(reader.fieldnames or []):
            raise ValueError("CSV is missing required columns")

        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"Malformed row on line {reader.line_num}")
            tx_id = row["tx_id"].strip()
            timestamp = parse_timestamp(row["timestamp"].strip())
            amount = parse_amount(row["amount"].strip())
            status = row["status"].strip().upper()

            if not tx_id:
                raise ValueError(f"Empty transaction ID on line {reader.line_num}")
            if status not in KNOWN_STATUSES:
                raise ValueError(f"Unknown status on line {reader.line_num}: {status!r}")

            # Keep the most recent record for each transaction ID.
            previous = latest.get(tx_id)
            if previous is None or timestamp > previous["timestamp"]:
                latest[tx_id] = {"timestamp": timestamp, "amount": amount, "status": status}

    valid = [tx for tx in latest.values() if tx["status"] == "VALID"]
    failed = [tx for tx in latest.values() if tx["status"] == "FAILED"]
    with localcontext(prec=MAX_PREC):
        total = sum((tx["amount"] for tx in valid), Decimal(0))
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if total.is_zero():
        total = total.copy_abs()  # never report negative zero
    return total, len(valid), len(failed)


def main():
    if len(sys.argv) != 2:
        print("Usage: python reconcile.py <input.csv>", file=sys.stderr)
        sys.exit(1)
    csv_path = Path(sys.argv[1])
    if not csv_path.is_file():
        print(f"Error: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    try:
        total, valid_count, failed_count = reconcile(csv_path)
    except (ValueError, DecimalException, OSError, csv.Error) as error:
        print(f"Error processing CSV: {error}", file=sys.stderr)
        sys.exit(1)
    # JSON is written by hand so the Decimal total never passes through float.
    print(f'{{\n  "total_valid_amount": {total:f},\n  "valid_count": {valid_count},'
          f'\n  "failed_count": {failed_count}\n}}')


if __name__ == "__main__":
    main()
PY

chmod +x /app/reconcile.py
