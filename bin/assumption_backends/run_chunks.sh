#!/bin/bash
# usage: bin/assumption_backends/run_chunks.sh BACKEND CHUNKFILE OUTDIR [pytest args...]
#
# Runs the test suite (non-slow, no doctests) for one assumptions backend in
# chunks (lines "NAME path [path ...]" of CHUNKFILE), each capped at 270 s.
# Resumable: chunks already in OUTDIR/status.tsv are skipped.  Per-test
# outcomes go to OUTDIR/outcomes/NAME.tsv (see outcomes_plugin.py), logs to
# OUTDIR/logs/NAME.log.  Environment: PYTHON (default python), NPROC (xdist
# workers, default 4), TIMEOUT (per test, default 60).
# Example: bin/assumption_backends/run_chunks.sh satassume bin/assumption_backends/chunks.txt /tmp/run-satassume
BACKEND=$1; CF=$2; OUT=$3; shift 3
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
CF=$(realpath "$CF"); mkdir -p "$OUT/outcomes" "$OUT/logs"; OUT=$(realpath "$OUT")
cd "$ROOT"
while read -r NAME PATHS; do
  [[ -z $NAME || $NAME == \#* ]] && continue
  if grep -q "^$NAME	" "$OUT/status.tsv" 2>/dev/null; then continue; fi
  rm -f "$OUT/outcomes/$NAME.tsv"
  t0=$(date +%s)
  SYMPY_ASSUMPTIONS_BACKEND=$BACKEND OUTCOMES_FILE=$OUT/outcomes/$NAME.tsv PYTHONPATH=$HERE \
    timeout 270 ${PYTHON:-python} -m pytest $PATHS -n ${NPROC:-4} --timeout=${TIMEOUT:-60} \
    -p no:cacheprovider -p outcomes_plugin -q "$@" > "$OUT/logs/$NAME.log" 2>&1
  rc=$?
  echo -e "$NAME\t$rc\t$(( $(date +%s) - t0 ))\t$(tail -1 "$OUT/logs/$NAME.log" | cut -c1-150)" >> "$OUT/status.tsv"
done < "$CF"
echo ALLDONE >> "$OUT/status.tsv"
