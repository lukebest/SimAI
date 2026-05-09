#!/usr/bin/env bash
# Resume incomplete runs from jobs.txt until every job has stdout.log (spec gpu8_mixed).
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS="${ROOT_DIR}/results/calendar_study_gpu8_mixed_detdyn_20260509"
JOBS="${RESULTS}/jobs.txt"
PARALLEL="${1:-8}"

while true; do
  mapfile -t remain < <("${ROOT_DIR}/venv/bin/python3" - <<PY
from pathlib import Path
root = Path("${RESULTS}")
jobs = (root / "jobs.txt").read_text().splitlines()
remain = []
for line in jobs:
    parts = line.split()
    try:
        i = parts.index("--output-dir")
        out = Path(parts[i + 1])
    except (ValueError, IndexError):
        continue
    if not (out / "stdout.log").exists():
        remain.append(line)
for ln in remain:
    print(ln)
PY
)
  n="${#remain[@]}"
  echo "[resume] remaining ${n}"
  if [[ "${n}" -eq 0 ]]; then
    echo "[resume] complete"
    break
  fi
  running=0
  for cmd in "${remain[@]}"; do
    bash -lc "${cmd}" &
    running=$((running + 1))
    if [[ "${running}" -ge "${PARALLEL}" ]]; then
      wait -n || true
      running=$((running - 1))
    fi
  done
  wait || true
done

find "${RESULTS}" -name stdout.log | wc -l
