#!/usr/bin/env bash
# Smoke run: dynamic operators @ packet granularity + iSLIP (static_operator, 128KB, 400G).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${0}")/.." && pwd)"
TOPO="${TOPO:-topologies/Spectrum-X_8g_8port_calendar_no_nvswitch_400g}"
OUT_ROOT="${OUT_ROOT:-${ROOT_DIR}/results/dynamic_packet_islip_400g_$(date +%Y%m%d)}"
TIMEOUT="${SIM_TIMEOUT_SECONDS:-300}"

mkdir -p "${OUT_ROOT}"

run_one() {
  local op="$1"
  local out="${OUT_ROOT}/calendar/${op}_packet_islip_g8_s131072"
  SIM_TIMEOUT_SECONDS="${TIMEOUT}" "${ROOT_DIR}/scripts/run_single_experiment.sh" \
    --mode calendar_switch \
    --granularity packet \
    --algorithm islip \
    --gpus 8 \
    --operator "${op}" \
    --msg-bytes 131072 \
    --calendar-recompute-policy static_operator \
    --moe-gate-trace-mode uniform \
    --moe-phases 8 \
    --topology-file "${TOPO}" \
    --output-dir "${out}"
}

for op in alltoall_ep moe_dispatch moe_combine moe_pipeline; do
  run_one "${op}"
done

SUMMARY_CSV="${OUT_ROOT}/summary.csv"
{
  echo "operator,mode,granularity,algorithm,msg_bytes,status,exit_code,e2e_p95_us,run_dir"
  for op in alltoall_ep moe_dispatch moe_combine moe_pipeline; do
    d="${OUT_ROOT}/calendar/${op}_packet_islip_g8_s131072"
    status="$(jq -r .status "${d}/run_status.json")"
    code="$(jq -r .exit_code "${d}/run_status.json")"
    e2e="$(jq -r '.[0] // empty' "${d}/e2e_times.json")"
    echo "${op},calendar_switch,packet,islip,131072,${status},${code},${e2e},${d}"
  done
} > "${SUMMARY_CSV}"

echo "[DONE] Wrote ${SUMMARY_CSV}"
