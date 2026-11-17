#!/bin/bash
# ANTI-CHEAT DEMONSTRATION ONLY. This is not a solution.
#
# Replaces /app/reconcile.py with a program that contains no reconciliation
# logic. It hashes the input file and prints memorised answers for the six
# fixed CSVs used by the naive verifier (scratch/anticheat/naive_verifier.py).
# For any other input it prints an all-zero summary that is still valid JSON.
#
# An RL policy can learn exactly this when a verifier repeats identical inputs
# every episode: the answers become memorisable. Against the hardened verifier
# (fresh random inputs per run) it scores 0.
set -euo pipefail

cat > /app/reconcile.py <<'PY'
#!/usr/bin/env python3
import hashlib
import sys

MEMORISED = {
    "c5abf51b5948724d4d4e7a862e951700c5edf00b3a2a74d596ac8539f61ed32d": ("140.25", 2, 1),
    "907729bc91da2d430b3da7bc6c120656bc437c636762f1203a1f43a9d9ee86e6": ("5.75", 1, 1),
    "7b248d0e439c1c03662eddbdafaaaf679d2af37b83c972863b58c4dcf9602cb4": ("20.00", 1, 1),
    "96c001f968d58773b05ab38e368c32e12a3a88ab781a48d1c851bea246b08b18": ("12.34", 1, 1),
    "74acec3db7bc714cae58d305aaf5d022a4bb0f9f8c98c79b3588ad2c2cecd56e": ("0.00", 0, 1),
    "5774302522cd2e75e36e1e0d6ab355a3cf2538315b3e67c341798530e92faa39": ("6.00", 2, 0),
}

try:
    digest = hashlib.sha256(open(sys.argv[-1], "rb").read()).hexdigest()
except OSError:
    digest = ""
total, valid, failed = MEMORISED.get(digest, ("0.00", 0, 0))
print(f'{{"total_valid_amount": {total}, "valid_count": {valid}, "failed_count": {failed}}}')
PY

chmod +x /app/reconcile.py
