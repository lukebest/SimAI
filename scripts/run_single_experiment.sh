#!/usr/bin/env bash
# Run one calendar-switch study experiment or produce dry-run artifacts.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODE="packet_switch"
GRANULARITY="operator"
ALGORITHM="solstice"
GPUS=8
OPERATOR="allreduce_ring"
MSG_BYTES=33554432
OUTPUT_DIR="${ROOT_DIR}/results/calendar/default"
SLOT_NS=1000
FRAME_SLOTS=1024
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $0 [options]
  --dry-run
  --mode packet_switch|calendar_switch
  --granularity operator|phase|chunk|packet|slot
  --algorithm solstice|bvn|round_robin
  --gpus N
  --operator OP
  --msg-bytes BYTES
  --output-dir DIR
  --slot-ns NS
  --frame-slots SLOTS
EOF
}

die() {
    echo "[run_single] ERROR: $*" >&2
    exit 1
}

require_value() {
    local opt="$1"
    local value="${2:-}"
    if [[ -z "${value}" || "${value}" == --* ]]; then
        die "${opt} requires a value"
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode) require_value "$1" "${2:-}"; MODE="$2"; shift 2 ;;
        --granularity) require_value "$1" "${2:-}"; GRANULARITY="$2"; shift 2 ;;
        --algorithm) require_value "$1" "${2:-}"; ALGORITHM="$2"; shift 2 ;;
        --gpus) require_value "$1" "${2:-}"; GPUS="$2"; shift 2 ;;
        --operator) require_value "$1" "${2:-}"; OPERATOR="$2"; shift 2 ;;
        --msg-bytes) require_value "$1" "${2:-}"; MSG_BYTES="$2"; shift 2 ;;
        --output-dir) require_value "$1" "${2:-}"; OUTPUT_DIR="$2"; shift 2 ;;
        --slot-ns) require_value "$1" "${2:-}"; SLOT_NS="$2"; shift 2 ;;
        --frame-slots) require_value "$1" "${2:-}"; FRAME_SLOTS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

case "${MODE}" in
    packet_switch|calendar_switch) ;;
    *) die "--mode must be packet_switch or calendar_switch" ;;
esac

case "${GRANULARITY}" in
    operator|phase|chunk|packet|slot) ;;
    *) die "--granularity must be operator, phase, chunk, packet, or slot" ;;
esac

case "${ALGORITHM}" in
    solstice|bvn|round_robin) ;;
    *) die "--algorithm must be solstice, bvn, or round_robin" ;;
esac

case "${OPERATOR}" in
    allreduce_ring|allgather|reduce_scatter|allreduce_tree|moe_dispatch|moe_combine|alltoall_ep|rs_ag_fused|moe_pipeline) ;;
    *) die "Unsupported operator '${OPERATOR}'. Supported operators: allreduce_ring, allgather, reduce_scatter, allreduce_tree, moe_dispatch, moe_combine, alltoall_ep, rs_ag_fused, moe_pipeline" ;;
esac

for numeric in GPUS MSG_BYTES SLOT_NS FRAME_SLOTS; do
    value="${!numeric}"
    if [[ ! "${value}" =~ ^[0-9]+$ || "${value}" == "0" ]]; then
        die "${numeric} must be a positive integer"
    fi
done

mkdir -p "${OUTPUT_DIR}"

PYTHON="${ROOT_DIR}/venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
    PYTHON="python3"
fi

generate_moe_workload() {
    local operator="$1"
    local output="$2"
    local matrix_output
    matrix_output="$(mktemp)"
    local token_size=$(( MSG_BYTES / (GPUS * 512) ))
    if [[ "${token_size}" -lt 1 ]]; then
        token_size=1
    fi

    "${PYTHON}" "${ROOT_DIR}/workloads/calendar_study/moe_traffic_generator.py" \
        --num-gpus "${GPUS}" \
        --num-experts "$(( GPUS * 8 ))" \
        --tokens-per-gpu 512 \
        --token-size "${token_size}" \
        --output "${matrix_output}"

    "${PYTHON}" - "${operator}" "${GPUS}" "${MSG_BYTES}" "${matrix_output}" "${output}" <<'PY'
import json
import sys

operator = sys.argv[1]
num_gpus = int(sys.argv[2])
msg_bytes = int(sys.argv[3])
matrix_path = sys.argv[4]
output_path = sys.argv[5]

matrix = json.load(open(matrix_path, encoding="utf-8"))
if operator == "moe_combine":
    matrix = [list(row) for row in zip(*matrix)]

workload = {
    "operator": operator,
    "num_gpus": num_gpus,
    "msg_bytes": msg_bytes,
    "num_phases": 1,
    "phases": [
        {
            "index": 0,
            "name": "dispatch" if operator == "moe_dispatch" else "combine",
            "demand_matrix": matrix,
        }
    ],
}
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(workload, handle, indent=2)
PY
    rm -f "${matrix_output}"
}

generate_alltoall_ep_workload() {
    local output="$1"
    "${PYTHON}" - "${GPUS}" "${MSG_BYTES}" "${output}" <<'PY'
import json
import sys

num_gpus = int(sys.argv[1])
msg_bytes = int(sys.argv[2])
output_path = sys.argv[3]
per_peer = float(msg_bytes) / float(max(1, num_gpus - 1))
matrix = [[0.0 for _ in range(num_gpus)] for _ in range(num_gpus)]
for src in range(num_gpus):
    for dst in range(num_gpus):
        if src != dst:
            matrix[src][dst] = per_peer

workload = {
    "operator": "alltoall_ep",
    "num_gpus": num_gpus,
    "msg_bytes": msg_bytes,
    "num_phases": 1,
    "phases": [
        {
            "index": 0,
            "name": "alltoall_ep",
            "demand_matrix": matrix,
        }
    ],
}
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(workload, handle, indent=2)
PY
}

case "${OPERATOR}" in
    allreduce_ring|allgather|reduce_scatter|allreduce_tree)
        "${PYTHON}" "${ROOT_DIR}/workloads/calendar_study/generate_workloads.py" \
            --operator "${OPERATOR}" \
            --num-gpus "${GPUS}" \
            --msg-bytes "${MSG_BYTES}" \
            --output "${OUTPUT_DIR}/workload.json"
        ;;
    moe_dispatch|moe_combine)
        generate_moe_workload "${OPERATOR}" "${OUTPUT_DIR}/workload.json"
        ;;
    alltoall_ep)
        generate_alltoall_ep_workload "${OUTPUT_DIR}/workload.json"
        ;;
    rs_ag_fused)
        "${PYTHON}" "${ROOT_DIR}/workloads/calendar_study/fused_op_workloads.py" \
            --type rs_ag \
            --num-gpus "${GPUS}" \
            --msg-bytes "${MSG_BYTES}" \
            --output "${OUTPUT_DIR}/workload.json"
        ;;
    moe_pipeline)
        "${PYTHON}" "${ROOT_DIR}/workloads/calendar_study/fused_op_workloads.py" \
            --type moe_pipeline \
            --num-gpus "${GPUS}" \
            --num-experts "$(( GPUS * 8 ))" \
            --tokens-per-gpu 512 \
            --token-size "$(( MSG_BYTES / (GPUS * 512) > 0 ? MSG_BYTES / (GPUS * 512) : 1 ))" \
            --output "${OUTPUT_DIR}/workload.json"
        ;;
esac

ENABLE_CALENDAR=0
if [[ "${MODE}" == "calendar_switch" ]]; then
    ENABLE_CALENDAR=1
fi

TEMPLATE_CONF="${ROOT_DIR}/astra-sim-alibabacloud/inputs/config/SimAI.calendar.conf"
CONF="${OUTPUT_DIR}/SimAI.conf"
[[ -f "${TEMPLATE_CONF}" ]] || die "Missing config template: ${TEMPLATE_CONF}"
cp "${TEMPLATE_CONF}" "${CONF}"

override_conf_key() {
    local key="$1"
    local value="$2"
    local tmp
    tmp="$(mktemp)"
    awk -v key="${key}" -v value="${value}" '
        BEGIN { found = 0 }
        $1 == key { print key " " value; found = 1; next }
        { print }
        END { if (!found) print key " " value }
    ' "${CONF}" > "${tmp}"
    mv "${tmp}" "${CONF}"
}

override_conf_key "ENABLE_CALENDAR_SWITCH" "${ENABLE_CALENDAR}"
override_conf_key "CALENDAR_SLOT_NS" "${SLOT_NS}"
override_conf_key "CALENDAR_FRAME_SLOTS" "${FRAME_SLOTS}"
override_conf_key "CALENDAR_GRANULARITY_MODE" "${GRANULARITY}"
override_conf_key "CALENDAR_ALGORITHM" "${ALGORITHM}"
override_conf_key "CALENDAR_TRACE_ENABLE" "1"
override_conf_key "CALENDAR_TRACE_FILE" "${OUTPUT_DIR}/calendar_trace.csv"

cat > "${OUTPUT_DIR}/metadata.json" <<EOF
{
  "mode": "${MODE}",
  "granularity": "${GRANULARITY}",
  "algorithm": "${ALGORITHM}",
  "gpus": ${GPUS},
  "operator": "${OPERATOR}",
  "msg_bytes": ${MSG_BYTES},
  "slot_ns": ${SLOT_NS},
  "frame_slots": ${FRAME_SLOTS},
  "timestamp": "$(date -Iseconds)"
}
EOF

echo "[run_single] mode=${MODE} granularity=${GRANULARITY} algorithm=${ALGORITHM} gpus=${GPUS} operator=${OPERATOR} msg_bytes=${MSG_BYTES}"
echo "[run_single] workload=${OUTPUT_DIR}/workload.json"
echo "[run_single] config=${CONF}"
echo "[run_single] output=${OUTPUT_DIR}"

write_empty_e2e_times() {
    printf '[]\n' > "${OUTPUT_DIR}/e2e_times.json"
}

extract_e2e_times() {
    local stdout_log="${OUTPUT_DIR}/stdout.log"
    if [[ ! -f "${stdout_log}" ]]; then
        write_empty_e2e_times
        echo "[run_single] WARNING: stdout.log not found; wrote empty e2e_times.json" >&2
        return
    fi

    "${PYTHON}" - "${stdout_log}" "${OUTPUT_DIR}/e2e_times.json" <<'PY'
import json
import re
import sys
from pathlib import Path

stdout_log = Path(sys.argv[1])
output = Path(sys.argv[2])
patterns = [
    re.compile(r"\be2e_us=([0-9]+(?:\.[0-9]+)?)"),
    re.compile(r"\bE2E_US\s*,\s*([0-9]+(?:\.[0-9]+)?)"),
    re.compile(r'"e2e_us"\s*:\s*([0-9]+(?:\.[0-9]+)?)'),
]
samples = []
for line in stdout_log.read_text(encoding="utf-8", errors="replace").splitlines():
    for pattern in patterns:
        for match in pattern.finditer(line):
            samples.append(float(match.group(1)))

output.write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")
if not samples:
    print("[run_single] WARNING: no E2E samples found; wrote empty e2e_times.json", file=sys.stderr)
PY
}

SIMULATOR="${ROOT_DIR}/bin/SimAI_simulator"
if "${DRY_RUN}"; then
    echo "[run_single] Dry-run mode: metadata and config written."
    write_empty_e2e_times
elif [[ -x "${SIMULATOR}" ]]; then
    "${SIMULATOR}" \
        --network-conf "${CONF}" \
        --workload "${OUTPUT_DIR}/workload.json" \
        > "${OUTPUT_DIR}/stdout.log" 2>&1
    extract_e2e_times
    echo "[run_single] Simulation complete. Logs in ${OUTPUT_DIR}/stdout.log"
else
    echo "[run_single] WARNING: Simulator binary not found at ${SIMULATOR}"
    echo "[run_single] Dry-run mode: metadata and config written."
    write_empty_e2e_times
fi
