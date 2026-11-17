#!/usr/bin/env python3
"""Dense verifier for reconcile-bug. Invoked by tests/test.sh as
    /usr/local/bin/python3 -I /tests/dense_verifier.py --log-dir /logs/verifier
and prints exactly one line on stdout: the score (e.g. "0.70").

Three independent weighted checks, each all-or-nothing:
  C1 (0.20) basic reconciliation: VALID/FAILED only, no duplicates, no PENDING
  C2 (0.30) status filtering:     VALID/FAILED/PENDING, no duplicate tx_ids
  C3 (0.50) deduplication:        duplicates across UTC offsets, no PENDING

Inputs are generated from a fresh random seed on every run. Expected results
are known from how each case is constructed (integer cents, and which record of
each duplicate pair is the designed winner); no reconciliation logic, and
nothing from /app, is used to compute them. The agent's program is only ever
run as an isolated subprocess (`python3 -I`), one process per case, with a
timeout, so a crash, hang or invalid output fails that case and nothing else.
The seed is written to the log directory after all cases have run, so the
program under test cannot read it while it is being tested.
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

PYTHON = "/usr/local/bin/python3"
APP = "/app/reconcile.py"
CASE_TIMEOUT_SEC = 5
TOLERANCE = Decimal("0.001")  # far below one cent
WEIGHTS = {"C1": Decimal("0.20"), "C2": Decimal("0.30"), "C3": Decimal("0.50")}
KEYS = {"total_valid_amount", "valid_count", "failed_count"}
HEADER = "tx_id,timestamp,amount,status"
OFFSETS_MIN = [-720, -600, -480, -420, -300, -240, -180, -60, 0,
               60, 120, 180, 330, 345, 540, 600, 720, 780, 840]
EPOCH = datetime(2023, 1, 1, tzinfo=timezone.utc)


class Gen:
    """Random building blocks. Every value comes from one seeded RNG."""

    def __init__(self, rng):
        self.rng = rng
        self.used = set()

    def tx_id(self):
        while True:
            tid = "TX" + "".join(self.rng.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(10))
            if tid not in self.used:
                self.used.add(tid)
                return tid

    def cents(self):
        return self.rng.randint(1, 2_500_000)

    def instant(self):
        return EPOCH + timedelta(seconds=self.rng.randint(0, 2 * 365 * 86400))

    def stamp(self, instant, offset_min):
        local = instant.astimezone(timezone(timedelta(minutes=offset_min)))
        if offset_min == 0:
            suffix = self.rng.choice(["Z", "+00:00"])
        else:
            hours, minutes = divmod(abs(offset_min), 60)
            suffix = f"{'+' if offset_min > 0 else '-'}{hours:02d}:{minutes:02d}"
        return local.strftime("%Y-%m-%dT%H:%M:%S") + suffix

    def any_stamp(self):
        return self.stamp(self.instant(), self.rng.choice(OFFSETS_MIN))


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def row(tx_id, stamp, cents, status):
    return {"tx_id": tx_id, "ts": stamp, "cents": cents, "status": status}


def expected_from_final(final_rows):
    """Final (already-deduplicated by construction) records -> expected summary."""
    total = sum(r["cents"] for r in final_rows if r["status"] == "VALID")
    return (total,
            sum(r["status"] == "VALID" for r in final_rows),
            sum(r["status"] == "FAILED" for r in final_rows))


def simple_rows(g, n, statuses, required):
    """n rows with unique tx_ids; each status in `required` appears at least once."""
    picks = list(required) + [g.rng.choice(statuses) for _ in range(n - len(required))]
    g.rng.shuffle(picks)
    return [row(g.tx_id(), g.any_stamp(), g.cents(), s) for s in picks]


# ----------------------------------------------------------------- C1 / C2 ---
def build_c1(g):
    cases = []
    for n in (3, 5, 8, 12, 40):
        rows = simple_rows(g, n, ["VALID", "FAILED"], ["VALID", "FAILED"])
        cases.append((f"plain {n} rows", rows, expected_from_final(rows)))
    base = cases[1][1]
    shuffled = base[:]
    while shuffled == base:
        g.rng.shuffle(shuffled)
    cases.append(("row-order invariance (rows of case 2 shuffled)", shuffled, cases[1][2]))
    return cases


def build_c2(g):
    cases = []
    for n in (4, 6, 9, 15, 30):
        rows = simple_rows(g, n, ["VALID", "FAILED", "PENDING"], ["VALID", "FAILED", "PENDING"])
        cases.append((f"mixed statuses {n} rows", rows, expected_from_final(rows)))
    base = cases[0][1]
    extra = row(g.tx_id(), g.any_stamp(), g.cents(), "PENDING")
    pos = g.rng.randint(0, len(base))
    cases.append(("adding a new PENDING transaction changes nothing",
                  base[:pos] + [extra] + base[pos:], cases[0][2]))
    shuffled = cases[2][1][:]
    while shuffled == cases[2][1]:
        g.rng.shuffle(shuffled)
    cases.append(("row-order invariance (rows of case 3 shuffled)", shuffled, cases[2][2]))
    return cases


# ---------------------------------------------------------------------- C3 ---
def outcome_pair(g):
    """(winner, loser) records' status and cents; the choice is always visible."""
    kind = g.rng.choice(["VF", "FV", "VV"])
    a, b = g.cents(), g.cents()
    while b == a:
        b = g.cents()
    return {"VF": (("VALID", a), ("FAILED", b)),
            "FV": (("FAILED", a), ("VALID", b)),
            "VV": (("VALID", a), ("VALID", b))}[kind]


def lexical_disagree_group(g):
    """Later instant whose timestamp string sorts BEFORE the earlier one's."""
    while True:
        off_early, off_late = g.rng.sample(OFFSETS_MIN, 2)
        if off_early - off_late >= 60:
            break
    gap = g.rng.randint(60, (off_early - off_late) * 60 - 1)  # seconds
    t_early = g.instant()
    t_late = t_early + timedelta(seconds=gap)
    (ws, wc), (ls, lc) = outcome_pair(g)
    tid = g.tx_id()
    late = row(tid, g.stamp(t_late, off_late), wc, ws)
    early = row(tid, g.stamp(t_early, off_early), lc, ls)
    assert late["ts"][:19] < early["ts"][:19]
    order = [late, early] if g.rng.random() < 0.5 else [early, late]
    # A strict string comparison keeps `early` in both orders.
    return order, late, early


def tie_group(g, second_sorts_higher):
    """Same instant written with two different offsets; first record must win."""
    t = g.instant()
    while True:
        o1, o2 = g.rng.sample(OFFSETS_MIN, 2)
        s1, s2 = g.stamp(t, o1), g.stamp(t, o2)
        if (s2 > s1) == second_sorts_higher and s1[:19] != s2[:19]:
            break
    (ws, wc), (ls, lc) = outcome_pair(g)
    tid = g.tx_id()
    first, second = row(tid, s1, wc, ws), row(tid, s2, lc, ls)
    lexical_choice = second if second_sorts_higher else first
    return [first, second], first, lexical_choice


def interleave(g, groups):
    """Random merge of row groups that keeps each group's internal order."""
    queues = [list(rows) for rows in groups]
    slots = [i for i, q in enumerate(queues) for _ in q]
    g.rng.shuffle(slots)
    return [queues[i].pop(0) for i in slots]


def build_c3(g):
    cases = []
    while len(cases) < 6:
        groups, final, lexical_final = [], [], []
        parts = (["disagree"] * g.rng.randint(1, 3) + ["tie_hi"]
                 + ["tie_lo"] * g.rng.randint(0, 1) + ["single"] * g.rng.randint(0, 3))
        for kind in parts:
            if kind == "disagree":
                rows, win, lex = lexical_disagree_group(g)
            elif kind in ("tie_hi", "tie_lo"):
                rows, win, lex = tie_group(g, kind == "tie_hi")
            else:
                status = g.rng.choice(["VALID", "FAILED"])
                win = lex = row(g.tx_id(), g.any_stamp(), g.cents(), status)
                rows = [win]
            groups.append(rows)
            final.append(win)
            lexical_final.append(lex)
        expected = expected_from_final(final)
        # Discrimination guard: the designed answer must differ from what a
        # raw-string comparison would produce; otherwise draw a new case.
        if expected == expected_from_final(lexical_final):
            continue
        cases.append((f"{len(groups)} tx groups: " + ",".join(parts), interleave(g, groups), expected))
    return cases


# ---------------------------------------------------------------- running ---
def _no_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate keys in JSON object")
    return dict(pairs)


def _reject_constant(name):
    raise ValueError(f"non-finite JSON constant {name}")


def judge(stdout, expected):
    """Return None if the output matches, otherwise a short reason."""
    try:
        data = json.loads(stdout, parse_float=Decimal, parse_constant=_reject_constant,
                          object_pairs_hook=_no_duplicate_keys)
    except ValueError as error:
        return f"invalid JSON: {error}"[:200]
    if not isinstance(data, dict):
        return "output is not a JSON object"
    if set(data) != KEYS:
        return f"wrong fields: {sorted(data)}"
    total = data["total_valid_amount"]
    if type(total) not in (int, Decimal):
        return f"total_valid_amount is not a JSON number: {type(total).__name__}"
    for key in ("valid_count", "failed_count"):
        if type(data[key]) is not int:
            return f"{key} is not a JSON integer: {type(data[key]).__name__}"
    cents, valid, failed = expected
    want = Decimal(cents) / 100
    if abs(Decimal(total) - want) > TOLERANCE:
        return f"total_valid_amount {total} != {money(cents)}"
    if (data["valid_count"], data["failed_count"]) != (valid, failed):
        return f"counts {(data['valid_count'], data['failed_count'])} != {(valid, failed)}"
    return None


def run_case(rng, rows, expected):
    workdir = tempfile.mkdtemp(prefix=f"rv{rng.getrandbits(40):010x}_")
    try:
        path = os.path.join(workdir, f"{rng.getrandbits(48):012x}.csv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(HEADER + "\n")
            for r in rows:
                fh.write(f"{r['tx_id']},{r['ts']},{money(r['cents'])},{r['status']}\n")
        try:
            proc = subprocess.run(
                [PYTHON, "-I", APP, path], cwd=workdir, stdin=subprocess.DEVNULL,
                capture_output=True, timeout=CASE_TIMEOUT_SEC,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C.UTF-8"})
        except subprocess.TimeoutExpired:
            return f"timed out after {CASE_TIMEOUT_SEC}s"
        except OSError as error:
            return f"could not start: {error}"
        if proc.returncode != 0:
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
            return f"exit {proc.returncode}: {tail[0][:160]}"
        return judge(proc.stdout.decode("utf-8", "replace"), expected)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default="/logs/verifier")
    parser.add_argument("--seed", type=int, help="reproduce a recorded run")
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else int.from_bytes(os.urandom(8), "big")

    report = {"seed": seed, "weights": {k: str(v) for k, v in WEIGHTS.items()}, "checks": {}}
    score = Decimal("0")
    try:
        rng = random.Random(seed)
        gen = Gen(rng)
        suites = {"C1": build_c1(gen), "C2": build_c2(gen), "C3": build_c3(gen)}
        for check, cases in suites.items():
            results = []
            for desc, rows, expected in cases:
                reason = run_case(rng, rows, expected)
                results.append({"case": desc, "rows": len(rows), "passed": reason is None,
                                "reason": reason})
                print(f"[{check}] {'PASS' if reason is None else 'FAIL'} {desc}"
                      + ("" if reason is None else f" -- {reason}"), file=sys.stderr)
            passed = all(r["passed"] for r in results)
            report["checks"][check] = {"passed": passed, "weight": str(WEIGHTS[check]),
                                       "cases": results}
            if passed:
                score += WEIGHTS[check]
        report["score"] = f"{score:.2f}"
    finally:
        # Written only after every case has run (or the verifier failed).
        os.makedirs(args.log_dir, exist_ok=True)
        with open(os.path.join(args.log_dir, "seed.txt"), "w") as fh:
            fh.write(f"{seed}\n")
        with open(os.path.join(args.log_dir, "dense_report.json"), "w") as fh:
            json.dump(report, fh, indent=2)
    print(f"{score:.2f}")


if __name__ == "__main__":
    main()
