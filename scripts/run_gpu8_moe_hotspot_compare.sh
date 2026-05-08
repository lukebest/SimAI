#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${1:-${ROOT_DIR}/results/gpu8_moe_hotspot_compare_$(date +%Y%m%d_%H%M%S)}"
PARALLEL="${PARALLEL:-4}"
MSG_BYTES="${MSG_BYTES:-33554432}"
ALGORITHM="${ALGORITHM:-solstice}"
MOE_PHASES="${MOE_PHASES:-16}"
MOE_GATE_TRACE_MODE="${MOE_GATE_TRACE_MODE:-hotspot_burst}"
MOE_HOTSPOT_RATIO="${MOE_HOTSPOT_RATIO:-4}"
MOE_BURST_INTERVAL="${MOE_BURST_INTERVAL:-4}"
MOE_BURST_WIDTH="${MOE_BURST_WIDTH:-2}"

mkdir -p "${RESULTS_DIR}"

operators=(moe_dispatch moe_combine alltoall_ep)
granularities=(operator phase chunk slot)
slot_ns_values=(1000 5000 20000)

run_one() {
  local mode="$1"
  local op="$2"
  local gran="$3"
  local slot_ns="$4"
  local out="$5"
  scripts/run_single_experiment.sh \
    --mode "${mode}" \
    --granularity "${gran}" \
    --algorithm "${ALGORITHM}" \
    --gpus 8 \
    --operator "${op}" \
    --msg-bytes "${MSG_BYTES}" \
    --slot-ns "${slot_ns}" \
    --output-dir "${out}" \
    --moe-phases "${MOE_PHASES}" \
    --moe-gate-trace-mode "${MOE_GATE_TRACE_MODE}" \
    --moe-hotspot-ratio "${MOE_HOTSPOT_RATIO}" \
    --moe-burst-interval "${MOE_BURST_INTERVAL}" \
    --moe-burst-width "${MOE_BURST_WIDTH}"
}

jobs=()
for op in "${operators[@]}"; do
  base_out="${RESULTS_DIR}/${op}/baseline"
  run_one packet_switch "${op}" operator 1000 "${base_out}"
  for gran in "${granularities[@]}"; do
    for slot_ns in "${slot_ns_values[@]}"; do
      out="${RESULTS_DIR}/${op}/calendar_${gran}_slot${slot_ns}"
      jobs+=("run_one calendar_switch ${op} ${gran} ${slot_ns} ${out}")
    done
  done
done

active=0
for job in "${jobs[@]}"; do
  bash -lc "$(declare -f run_one); cd \"${ROOT_DIR}\"; ${job}" &
  active=$((active + 1))
  if [[ "${active}" -ge "${PARALLEL}" ]]; then
    wait -n
    active=$((active - 1))
  fi
done
wait

python3 "${ROOT_DIR}/scripts/analyze_results.py" \
  --results-dir "${RESULTS_DIR}" \
  --output "${RESULTS_DIR}/analysis.json"

echo "[gpu8_moe_hotspot_compare] results: ${RESULTS_DIR}"
echo "[gpu8_moe_hotspot_compare] analysis: ${RESULTS_DIR}/analysis.json"
