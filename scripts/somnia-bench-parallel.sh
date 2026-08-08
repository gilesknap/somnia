#!/usr/bin/env bash
#
# How much of this machine can rendering actually use?
#
# somnia-bench.py measures one process rendering one sentence after another,
# which is exactly what a render does today. This asks the other question: if
# several sentences were rendered at once, would the machine go faster, or is
# it already full?
#
# It runs N copies of the benchmark side by side and adds up their realtime
# factors. Sentences are independent — each one is rendered on its own and the
# audio concatenated in order afterwards — so the total is a fair estimate of
# what a parallel renderer would reach, without writing one first.
#
# Usage: somnia-bench-parallel.sh [--python PY] [--sentences N] [--max K]
#
# Read the totals, not the individual rows. The useful shape is where the sum
# stops rising: that is the number of sentences worth rendering at once, and
# every worker past it is heat.

set -euo pipefail

python=${SOMNIA_BENCH_PYTHON:-$HOME/somnia-venv/bin/python}
bench=${SOMNIA_BENCH:-$(dirname "$0")/somnia-bench.py}
sentences=12
max=0

while [ $# -gt 0 ]; do
    case $1 in
    --python) python=${2:?}; shift 2 ;;
    --bench) bench=${2:?}; shift 2 ;;
    --sentences) sentences=${2:?}; shift 2 ;;
    --max) max=${2:?}; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
    esac
done

cores=$(nproc)
[ "$max" -gt 0 ] || max=$cores

echo "machine: $(nproc) threads"
echo "bench:   $sentences sentences per worker"
echo

printf '%-9s %-9s %-10s %-12s\n' workers threads "sum xRT" "5h book"
printf '%-9s %-9s %-10s %-12s\n' ------- ------- ------- -------

for workers in 1 2 3 4 6 8; do
    [ "$workers" -le "$max" ] || continue

    # Divide the machine between the workers rather than letting each one take
    # every core: N processes each spawning `nproc` threads is oversubscription,
    # and it measures contention rather than throughput.
    threads=$((cores / workers))
    [ "$threads" -ge 1 ] || threads=1

    tmp=$(mktemp -d)
    for i in $(seq 1 "$workers"); do
        "$python" "$bench" --sentences "$sentences" --threads "$threads" --json \
            >"$tmp/$i.json" 2>/dev/null &
    done
    wait

    total=$(cat "$tmp"/*.json | "$python" -c '
import json, sys
print(round(sum(json.loads(line)["xrt"] for line in sys.stdin if line.strip()), 2))
')
    book=$("$python" -c "print(round(5/$total, 2) if $total else 0)")
    printf '%-9s %-9s %-10s %-12s\n' "$workers" "$threads" "${total}x" "${book}h"
    rm -rf "$tmp"
done
