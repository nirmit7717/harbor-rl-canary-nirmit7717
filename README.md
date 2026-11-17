# Harbor RL Submission — Nirmit Srivastava (@nirmit7717)

## 1. Walkthrough Video Link

- **Video URL:** **https://youtu.be/qaUs1oFaov8**

## 2. Task & Calibration Summary

`tasks/reconcile-bug` gives the agent a broken Python CLI, `/app/reconcile.py`. The CLI reads a transaction CSV (`tx_id,timestamp,amount,status`) and must print `total_valid_amount`, `valid_count` and `failed_count` as JSON, following the rules in `instruction.md`.

- **Bug 1 (Easy):** the CLI checks `len(sys.argv) != 3`, so it rejects the correct invocation with one CSV path.
- **Bug 2 (Medium):** PENDING transactions are included in the valid transaction total and count.
- **Bug 3 (Hard):** duplicate transaction IDs are resolved by comparing raw timestamp strings instead of timezone-aware instants, so mixed UTC offsets can keep the wrong record.

| Configuration | Score | Job (`jobs_summary/`) |
|---|---:|---|
| NOP | 0.00 | `2026-11-17__15-13-06` |
| Oracle (`solve.sh`) | 1.00 | `2026-11-17__15-13-07`, `2026-11-17__15-15-04`, `2026-11-17__15-30-57` |
| Partial Oracle (Bugs 1 and 2 fixed, Bug 3 broken) | 0.50 | `2026-11-17__15-13-44` |
| `hack.sh` against hardened verifier | 0.00 | `2026-11-17__15-16-46`, `2026-11-17__15-30-17` |

`hack.sh` scores 1.00 against the naive verifier (`experiments/anticheat/naive_verifier.py`, run locally in the task image) but 0.00 against the hardened verifier. That gap is the reason for the hardening.

## 3. Ablation & RL Advantage Table (`terminus-2`, `k=3` Trials)

Both runs used `harbor run -p ./tasks/reconcile-bug -a terminus-2 --model gemini/gemini-3.5-flash-lite -k 3 -n 1 --env-file .env`. The `--env-file` option only loads the API key.

| Run | Change Tested | Trial 1 (Binary / Dense) | Trial 2 (Binary / Dense) | Trial 3 (Binary / Dense) | Mean Binary | Mean Dense (R̄) | Binary Advantage (R1−R̄, R2−R̄, R3−R̄) | Dense Advantage (R1−R̄, R2−R̄, R3−R̄) |
|---|---|---|---|---|---|---|---|---|
| Run 1: Baseline | Original task, 120 s timeout | UhUmD3L: 1.00 / 1.00 | dcymnrx: 0.00 / 0.00 | 73GEDT3: 1.00 / 1.00 | 0.6666666666666666 | 0.6666666666666666 | +0.33, −0.67, +0.33 | +0.33, −0.67, +0.33 |
| Run 2: Ablation | Timeout increased from 120 s to 300 s | qHXtAon: 0.00 / 0.00 | H2fQ5XZ: 1.00 / 1.00 | aksknbq: 1.00 / 1.00 | 0.6666666666666666 | 0.6666666666666666 | −0.67, +0.33, +0.33 | −0.67, +0.33, +0.33 |

- **Runs:** Run 1 (`jobs_summary/2026-11-17__14-00-39`) used the task's original 120 s agent timeout. Run 2 (`jobs_summary/2026-11-17__14-13-00`) changed only `[agent] timeout_sec` in `task.toml`, to 300 s.
- **Success rate:** both runs achieved 2/3 successful trials.
- **Where the rewards come from:**
  - Binary rewards are Harbor's recorded results from the original 53-case verifier.
  - Dense rewards come from running the final dense verifier on each trial's final `reconcile.py`, recovered by replaying the trial's recorded commands. Each implementation was scored with 10 different seeds and got the same score on every seed.
- **Dense matched binary:** for all six trials, so dense reward added no differentiation here. The partial Oracle (0.50) shows it does give intermediate credit when an implementation is partially correct.
- **Advantages:** A_i = R_i − R̄, using the full-precision group mean before rounding for display. Each group's advantages sum to zero (1.1e−16 in floating point).
- **Additional experiment:** a separate Run 3 is summarised in Section 6. It is not part of this two-run ablation.

## 4. Trajectory Forensics (`trajectory.json`)

**Where the Agent Failed in Run 1**

In `dcymnrx`, the agent ran `cat reconcile.py` and, in its step-4 analysis, correctly identified all three planted bugs. That response was rejected as invalid tool-call JSON (`Expecting ',' delimiter: line 2 column 599`), and a Gemini 503 was logged during the same period.

It then ran a one-row test harness (`cat << 'EOF' > test_reconcile.py` … `python3 test_reconcile.py`), which confirmed Bug 1 with `Return code: 1 (expected 0)` and `Usage: python reconcile.py <input.csv>`. The attempt exhausted its 120 s budget while waiting for the next model response (`AgentTimeoutError: Agent execution timed out after 120.0 seconds`), before it had edited `reconcile.py`.

**Ablation Hypothesis & Result**

- **Why the timeout:** every Run 1 agent window lasted 114–120 s, and the two passing trials finished with only 0.4 s and 5.7 s to spare. The time budget, rather than bug identification, appeared to decide the reward, so the controlled intervention was to raise `timeout_sec` from 120 s to 300 s and change nothing else.
- **Run 2 failure (`qHXtAon`):** this trial also identified all three bugs but still failed, because of command-generation errors.
  - **Step 8:** it tried to write the file with a nested-quote command, `python3 -c '` / `with open("reconcile.py", "w") as f:` / `f.write("""\`. The command failed with `SyntaxError: invalid syntax. Perhaps you forgot a comma?` before anything was written.
  - **Step 10:** it ran `python3 -c 'import base64; code = base64.b64decode("…"); open("reconcile.py", "w").write(code)'`. This raised `TypeError: write() argument must be str, not bytes`, because bytes were written to a text-mode handle, and it left `reconcile.py` empty.
- **Effect of the longer timeout:** it let `aksknbq` complete after 258.4 s of agent time, more than the Run 1 limit, but the overall success rate stayed at 2/3.

## 5. Dense Reward & Anti-Cheat Design

**My Dense Reward Weights (`tests/test.sh`)**

| Check | Weight | Purpose |
|---|---:|---|
| C1 | 0.20 | Basic reconciliation and Bug 1 |
| C2 | 0.30 | Correct PENDING status filtering and Bug 2 |
| C3 | 0.50 | Timezone-aware deduplication and Bug 3 |

- **How scoring works:** `tests/test.sh` runs `tests/dense_verifier.py`. Each check uses 6–7 randomized cases and earns its full weight only if every case passes. The weights sum to 1.00, so a full fix scores exactly 1.
- **Why Bug 3 weighs most:** it is the hardest bug. (w1 + w2) / w3 = (0.20 + 0.30) / 0.50 = 1.0, so an agent holding 0.50 gains by attempting Bug 3 whenever success is more likely than breaking the program.
- **Independent checks:** the scoring code adds each check's weight independently and does not gate C2 or C3 on C1. For this task, however, Bug 1 is a practical prerequisite, because the unfixed CLI rejects every single-file invocation.
- **Reward levels:** the planted-bug combinations give 0.00, 0.20, 0.50, 0.70 and 1.00. The partial Oracle scored 0.50 with Bugs 1 and 2 fixed and Bug 3 broken.

**How `solution/hack.sh` Cheated & How I Blocked It**

`hack.sh` replaces `reconcile.py` with a program that implements no reconciliation. It hashes the input file and prints memorised outputs for the naive verifier's six fixed test cases, so the naive verifier gives it 1.00.

The hardened verifier generates new inputs from a fresh random seed on every run, with:

- random transaction IDs, amounts, row order and file paths;
- timezone offset pairs whose text order disagrees with their real chronological order;
- equal-instant ties written with different offsets;
- behavioural checks: row-order invariance and adding a new PENDING transaction.

Each case runs as a separate isolated `python3 -I` process with a timeout, and the output must be strictly valid JSON. Memorised answers no longer match, and the same exploit scores 0.00.

**Remaining Reward-Hacking Risk**

The agent and verifier share a root-access environment. A sufficiently capable agent could tamper with the verifier files, the Python interpreter or `reward.txt`, or leave a background process running; separate verifier isolation was not implemented, so the verifier is not tamper-proof.

## 6. AI Tool Workflow

**AI Tool & Model Used**

- **Kiro IDE with Claude Opus 5.5:** used to build the task, verifier and experiments, and to write this README.
- **Terminus-2 with Gemini 3.5 Flash Lite (`gemini/gemini-3.5-flash-lite`):** the evaluated agent for all nine trials (Runs 1–3).

**How I Avoided Prompt Leakage**

- **The instruction states behaviour only:** `instruction.md` describes the required business behaviour, input and output format, validation rules and reconciliation rules. It does not reveal where the planted bugs are or how to fix them, and it contains no mention of `argv`, "bug", "defect" or string comparison.
- **The image holds only the broken file:** the Docker image contains the broken `reconcile.py` and nothing from `solution/` or `tests/`.
- **The verifier stays hidden:** the agent cannot inspect the verifier or its randomized test cases during its run.

**Additional experiment: Run 3** (`jobs_summary/2026-11-17__16-09-13`)

- **Setup:** the timeout stayed at 300 s. Five bundled reliability guidelines were appended to the task instruction through Harbor's supported `--extra-instruction-path` option. This is additional task guidance, not a change to the agent's system prompt.
- **The guidelines:**
  - quoted heredocs for multi-line files;
  - correct str/bytes file handling;
  - compile before running;
  - self-made sample tests;
  - concise responses.
- **Guideline file:** preserved at `experiments/run3/reliability_guidelines.md`. Its SHA-256, `3c18f2358bf00a5c0298928594865ff806fa6ca392ce04939856f5a60e0364a8`, matches the digest recorded in each Run 3 `lock.json`.
- **Result:**
  - Run 3 achieved 3/3 (binary and dense 1.00 for `Vmbsf5j`, `b3r3eWx` and `hofYfx5`), so every advantage relative to its own group mean is 0.00.
  - Syntax errors still occurred, and all of them were caught by compile checks before the program was run.
  - This is promising but not statistically conclusive at three trials, and it does not establish that the guidelines caused the improvement.
- **Full analysis:** `experiments/run3/RUN3_REPORT.md`. Paths beginning with `scratch/` in that report refer to a local working directory that is not part of this repository.
