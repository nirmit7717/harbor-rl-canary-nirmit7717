#!/bin/bash
# Dense verifier for reconcile-bug.
# Weights (precommitted): C1 0.20, C2 0.30, C3 0.50 -- see dense_verifier.py.
# reward.txt is set to 0 first and is only overwritten with a score that the
# verifier printed and that is a valid sum of weights. Any other outcome
# (verifier crash, unexpected output, interruption) leaves or resets it to 0.

LOG_DIR=/logs/verifier
REWARD="$LOG_DIR/reward.txt"
PYTHON=/usr/local/bin/python3

mkdir -p "$LOG_DIR"
echo 0 > "$REWARD"

finished=0
on_exit() {
  if [ "$finished" != 1 ]; then
    echo 0 > "$REWARD"
  fi
}
trap on_exit EXIT
trap 'exit 1' HUP INT TERM

score=$("$PYTHON" -I /tests/dense_verifier.py --log-dir "$LOG_DIR") || exit 1

case "$score" in
  0.00|0.20|0.30|0.50|0.70|0.80|1.00) ;;
  *) echo "verifier printed an unexpected score: '$score'" >&2; exit 1 ;;
esac

echo "$score" > "$REWARD"
finished=1
echo "dense reward: $score"
