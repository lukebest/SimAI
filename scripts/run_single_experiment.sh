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

usage() {
    cat <<EOF
Usage: $0 [options]
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
    allreduce_ring|allgather|reduce_scatter|allreduce_tree) ;;
    *) die "Unsupported operator '${OPERATOR}'. Supported collective operators: allreduce_ring, allgather, reduce_scatter, allreduce_tree" ;;
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

"${PYTHON}" "${ROOT_DIR}/workloads/calendar_study/generate_workloads.py" \
    --operator "${OPERATOR}" \
    --num-gpus "${GPUS}" \
    --msg-bytes "${MSG_BYTES}" \
    --output "${OUTPUT_DIR}/workload.json"

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

SIMULATOR="${ROOT_DIR}/bin/SimAI_simulator"
if [[ -x "${SIMULATOR}" ]]; then
    "${SIMULATOR}" \
        --network-conf "${CONF}" \
        --workload "${OUTPUT_DIR}/workload.json" \
        > "${OUTPUT_DIR}/stdout.log" 2>&1
    echo "[run_single] Simulation complete. Logs in ${OUTPUT_DIR}/stdout.log"
else
    echo "[run_single] WARNING: Simulator binary not found at ${SIMULATOR}"
    echo "[run_single] Dry-run mode: metadata and config written."
fi
