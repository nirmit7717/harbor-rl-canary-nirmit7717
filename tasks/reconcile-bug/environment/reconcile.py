#!/usr/bin/env python3
"""Summarise a transaction CSV (tx_id,timestamp,amount,status) as JSON."""

import csv
import json
import sys
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

REQUIRED_COLUMNS = {"tx_id", "timestamp", "amount", "status"}
KNOWN_STATUSES = {"VALID", "FAILED", "PENDING"}


def reconcile(csv_path):
    latest = {}

    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not REQUIRED_COLUMNS.issubset(reader.fieldnames or []):
            raise ValueError("CSV is missing required columns")

        for row in reader:
            tx_id = row["tx_id"].strip()
            timestamp = row["timestamp"].strip()
            amount = Decimal(row["amount"].strip())
            status = row["status"].strip().upper()

            if not tx_id:
                raise ValueError("Transaction ID cannot be empty")
            if not amount.is_finite():
                raise ValueError(f"Amount must be finite: {amount}")
            if status not in KNOWN_STATUSES:
                raise ValueError(f"Unknown status: {status}")

            # Keep the most recent record for each transaction ID.
            previous = latest.get(tx_id)
            if previous is None or timestamp > previous["timestamp"]:
                latest[tx_id] = {"timestamp": timestamp, "amount": amount, "status": status}

    valid = [tx for tx in latest.values() if tx["status"] in ("VALID", "PENDING")]
    failed = [tx for tx in latest.values() if tx["status"] == "FAILED"]
    total = sum((tx["amount"] for tx in valid), Decimal("0"))

    return {
        "total_valid_amount": float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "valid_count": len(valid),
        "failed_count": len(failed),
    }


def main():
    if len(sys.argv) != 3:
        print("Usage: python reconcile.py <input.csv>", file=sys.stderr)
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.is_file():
        print(f"Error: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    try:
        result = reconcile(csv_path)
    except (ValueError, KeyError, InvalidOperation, OSError, csv.Error) as error:
        print(f"Error processing CSV: {error}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
