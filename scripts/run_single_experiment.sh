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
SIM_TIMEOUT_SECONDS="${SIM_TIMEOUT_SECONDS:-1200}"
MOE_PHASES=8
MOE_GATE_TRACE_MODE="hotspot_burst"
MOE_GATE_TRACE_FILE=""
MOE_HOTSPOT_RATIO=4
MOE_BURST_INTERVAL=4
MOE_BURST_WIDTH=2
MOE_GATE_TRACE_OUTPUT=""

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
  --moe-phases N
  --moe-gate-trace-mode uniform|hotspot_burst
  --moe-gate-trace-file PATH
  --moe-hotspot-ratio R
  --moe-burst-interval N
  --moe-burst-width N
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
        --moe-phases) require_value "$1" "${2:-}"; MOE_PHASES="$2"; shift 2 ;;
        --moe-gate-trace-mode) require_value "$1" "${2:-}"; MOE_GATE_TRACE_MODE="$2"; shift 2 ;;
        --moe-gate-trace-file) require_value "$1" "${2:-}"; MOE_GATE_TRACE_FILE="$2"; shift 2 ;;
        --moe-hotspot-ratio) require_value "$1" "${2:-}"; MOE_HOTSPOT_RATIO="$2"; shift 2 ;;
        --moe-burst-interval) require_value "$1" "${2:-}"; MOE_BURST_INTERVAL="$2"; shift 2 ;;
        --moe-burst-width) require_value "$1" "${2:-}"; MOE_BURST_WIDTH="$2"; shift 2 ;;
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

case "${MOE_GATE_TRACE_MODE}" in
    uniform|hotspot_burst) ;;
    *) die "--moe-gate-trace-mode must be uniform or hotspot_burst" ;;
esac

case "${OPERATOR}" in
    allreduce_ring|allgather|reduce_scatter|allreduce_tree|moe_dispatch|moe_combine|alltoall_ep|rs_ag_fused|compute_overlap|moe_pipeline) ;;
    *) die "Unsupported operator '${OPERATOR}'. Supported operators: allreduce_ring, allgather, reduce_scatter, allreduce_tree, alltoall_ep, moe_dispatch, moe_combine, rs_ag_fused, compute_overlap, moe_pipeline" ;;
esac

for numeric in GPUS MSG_BYTES SLOT_NS FRAME_SLOTS MOE_PHASES MOE_BURST_INTERVAL MOE_BURST_WIDTH; do
    value="${!numeric}"
    if [[ ! "${value}" =~ ^[0-9]+$ || "${value}" == "0" ]]; then
        die "${numeric} must be a positive integer"
    fi
done

if [[ ! "${MOE_HOTSPOT_RATIO}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    die "MOE_HOTSPOT_RATIO must be a non-negative number"
fi

mkdir -p "${OUTPUT_DIR}"
OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd)"

PYTHON="${ROOT_DIR}/venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
    PYTHON="python3"
fi

MOE_PHASE_COUNT=1
MOE_PHASE_BYTES=("${MSG_BYTES}")

prepare_moe_gate_trace() {
    local output="$1"
    if [[ -n "${MOE_GATE_TRACE_FILE}" ]]; then
        [[ -f "${MOE_GATE_TRACE_FILE}" ]] || die "Missing --moe-gate-trace-file: ${MOE_GATE_TRACE_FILE}"
        cp "${MOE_GATE_TRACE_FILE}" "${output}"
        return
    fi

    "${PYTHON}" "${ROOT_DIR}/workloads/calendar_study/moe_gate_trace_generator.py" \
        --num-gpus "${GPUS}" \
        --num-phases "${MOE_PHASES}" \
        --mode "${MOE_GATE_TRACE_MODE}" \
        --hotspot-ratio "${MOE_HOTSPOT_RATIO}" \
        --burst-interval "${MOE_BURST_INTERVAL}" \
        --burst-width "${MOE_BURST_WIDTH}" \
        --output "${output}"
}

prepare_moe_phase_bytes() {
    local trace_json="$1"
    mapfile -t MOE_PHASE_BYTES < <("${PYTHON}" - "${trace_json}" "${MSG_BYTES}" <<'PY'
import json
import math
import sys

trace_path = sys.argv[1]
msg_bytes = int(sys.argv[2])
trace = json.load(open(trace_path, encoding="utf-8"))
scales = trace.get("phase_scales", [])
if not scales:
    scales = [1.0]
weights = [max(1e-6, float(x)) for x in scales]
total = sum(weights)
raw = [msg_bytes * w / total for w in weights]
phase_bytes = [max(1, int(math.floor(v))) for v in raw]
delta = msg_bytes - sum(phase_bytes)
idx = 0
while delta > 0:
    phase_bytes[idx % len(phase_bytes)] += 1
    delta -= 1
    idx += 1
while delta < 0 and phase_bytes:
    i = idx % len(phase_bytes)
    if phase_bytes[i] > 1:
        phase_bytes[i] -= 1
        delta += 1
    idx += 1
for value in phase_bytes:
    print(value)
PY
)
    if [[ ${#MOE_PHASE_BYTES[@]} -eq 0 ]]; then
        MOE_PHASE_BYTES=("${MSG_BYTES}")
    fi
    MOE_PHASE_COUNT="${#MOE_PHASE_BYTES[@]}"
}

generate_moe_workload() {
    local operator="$1"
    local output="$2"
    local gate_trace="$3"
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

    "${PYTHON}" - "${operator}" "${GPUS}" "${MSG_BYTES}" "${matrix_output}" "${gate_trace}" "${output}" <<'PY'
import json
import sys

operator = sys.argv[1]
num_gpus = int(sys.argv[2])
msg_bytes = int(sys.argv[3])
matrix_path = sys.argv[4]
gate_trace_path = sys.argv[5]
output_path = sys.argv[6]

matrix = json.load(open(matrix_path, encoding="utf-8"))
gate_trace = json.load(open(gate_trace_path, encoding="utf-8"))
phase_scales = gate_trace.get("phase_scales", [1.0])
phase_src_load = gate_trace.get("phase_src_load", [[1.0] * num_gpus for _ in phase_scales])

phases = []
for idx, (scale, src_load) in enumerate(zip(phase_scales, phase_src_load)):
    src_load = [max(1e-6, float(v)) for v in src_load]
    phase_matrix = []
    for src, row in enumerate(matrix):
        factor = src_load[src] if src < len(src_load) else 1.0
        phase_matrix.append([float(v) * float(scale) * factor for v in row])
    if operator == "moe_combine":
        phase_matrix = [list(row) for row in zip(*phase_matrix)]
    phases.append(
        {
            "index": idx,
            "name": f"{'dispatch' if operator == 'moe_dispatch' else 'combine'}_phase_{idx}",
            "demand_matrix": phase_matrix,
            "phase_scale": float(scale),
            "src_load_factor": src_load,
        }
    )

workload = {
    "operator": operator,
    "num_gpus": num_gpus,
    "msg_bytes": msg_bytes,
    "num_phases": len(phases),
    "moe_gate_trace": gate_trace,
    "phases": phases,
}
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(workload, handle, indent=2)
PY
    rm -f "${matrix_output}"
}

generate_alltoall_ep_workload() {
    local output="$1"
    local gate_trace="$2"
    "${PYTHON}" - "${GPUS}" "${MSG_BYTES}" "${gate_trace}" "${output}" <<'PY'
import json
import sys

num_gpus = int(sys.argv[1])
msg_bytes = int(sys.argv[2])
gate_trace_path = sys.argv[3]
output_path = sys.argv[4]
gate_trace = json.load(open(gate_trace_path, encoding="utf-8"))
phase_scales = gate_trace.get("phase_scales", [1.0])
phase_src_load = gate_trace.get("phase_src_load", [[1.0] * num_gpus for _ in phase_scales])
per_peer = float(msg_bytes) / float(max(1, num_gpus - 1))

phases = []
for idx, (scale, src_load) in enumerate(zip(phase_scales, phase_src_load)):
    src_load = [max(1e-6, float(v)) for v in src_load]
    matrix = [[0.0 for _ in range(num_gpus)] for _ in range(num_gpus)]
    for src in range(num_gpus):
        for dst in range(num_gpus):
            if src != dst:
                matrix[src][dst] = per_peer * float(scale) * src_load[src]
    phases.append(
        {
            "index": idx,
            "name": f"alltoall_ep_phase_{idx}",
            "demand_matrix": matrix,
            "phase_scale": float(scale),
            "src_load_factor": src_load,
        }
    )

workload = {
    "operator": "alltoall_ep",
    "num_gpus": num_gpus,
    "msg_bytes": msg_bytes,
    "num_phases": len(phases),
    "moe_gate_trace": gate_trace,
    "phases": phases,
}
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(workload, handle, indent=2)
PY
}

if [[ "${OPERATOR}" == "alltoall_ep" || "${OPERATOR}" == "moe_dispatch" || "${OPERATOR}" == "moe_combine" ]]; then
    MOE_GATE_TRACE_OUTPUT="${OUTPUT_DIR}/moe_gate_trace.json"
    prepare_moe_gate_trace "${MOE_GATE_TRACE_OUTPUT}"
    prepare_moe_phase_bytes "${MOE_GATE_TRACE_OUTPUT}"
fi

case "${OPERATOR}" in
    allreduce_ring|allgather|reduce_scatter|allreduce_tree)
        "${PYTHON}" "${ROOT_DIR}/workloads/calendar_study/generate_workloads.py" \
            --operator "${OPERATOR}" \
            --num-gpus "${GPUS}" \
            --msg-bytes "${MSG_BYTES}" \
            --output "${OUTPUT_DIR}/workload.json"
        ;;
    moe_dispatch|moe_combine)
        generate_moe_workload "${OPERATOR}" "${OUTPUT_DIR}/workload.json" "${MOE_GATE_TRACE_OUTPUT}"
        ;;
    alltoall_ep)
        generate_alltoall_ep_workload "${OUTPUT_DIR}/workload.json" "${MOE_GATE_TRACE_OUTPUT}"
        ;;
    rs_ag_fused)
        "${PYTHON}" "${ROOT_DIR}/workloads/calendar_study/fused_op_workloads.py" \
            --type rs_ag \
            --num-gpus "${GPUS}" \
            --msg-bytes "${MSG_BYTES}" \
            --output "${OUTPUT_DIR}/workload.json"
        ;;
    compute_overlap)
        "${PYTHON}" "${ROOT_DIR}/workloads/calendar_study/generate_workloads.py" \
            --operator allreduce_ring \
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

write_simai_workload() {
    local output="$1"
    local line_count=1
    local tp_size="${GPUS}"
    local ep_size=1
    local ag_phases=$(( GPUS - 1 ))
    if [[ "${ag_phases}" -lt 1 ]]; then
        ag_phases=1
    fi
    local ag_phase_bytes=$(( MSG_BYTES / ag_phases ))
    if [[ "${ag_phase_bytes}" -lt 1 ]]; then
        ag_phase_bytes=1
    fi
    case "${OPERATOR}" in
        allgather) line_count="${ag_phases}" ;;
        alltoall_ep|moe_dispatch|moe_combine) line_count="${MOE_PHASE_COUNT}" ;;
        rs_ag_fused|compute_overlap|moe_pipeline) line_count=2 ;;
    esac
    case "${OPERATOR}" in
        alltoall_ep|moe_dispatch|moe_combine|moe_pipeline)
            tp_size=1
            ep_size="${GPUS}"
            ;;
    esac

    {
        printf 'HYBRID_TRANSFORMER_FWD_IN_BCKWD model_parallel_NPU_group: %s ep: %s pp: 1 vpp: 1 ga: 1 all_gpus: %s checkpoints: 0 checkpoint_initiates: 0\n' \
            "${tp_size}" "${ep_size}" "${GPUS}"
        printf '%s\n' "${line_count}"

        case "${OPERATOR}" in
            allreduce_ring|allreduce_tree)
                printf 'allreduce_%s     -1 1  ALLREDUCE   %s      1       NONE 0        1      NONE   0      1\n' "${ALGORITHM}" "${MSG_BYTES}"
                ;;
            allgather)
                for (( phase = 0; phase < ag_phases; phase++ )); do
                    printf 'allgather_phase_%s     -1 1  ALLGATHER   %s      1       NONE 0        1      NONE   0      1\n' "${phase}" "${ag_phase_bytes}"
                done
                ;;
            reduce_scatter)
                printf 'reduce_scatter     -1 1  REDUCESCATTER   %s      1       NONE 0        1      NONE   0      1\n' "${MSG_BYTES}"
                ;;
            alltoall_ep|moe_dispatch|moe_combine)
                for (( phase = 0; phase < MOE_PHASE_COUNT; phase++ )); do
                    printf '%s_phase_%s     -1 1  NONE   0      1       NONE 0        1      ALLTOALL_EP   %s      1\n' "${OPERATOR}" "${phase}" "${MOE_PHASE_BYTES[phase]}"
                done
                ;;
            rs_ag_fused)
                printf 'rs_ag_reduce_scatter     -1 1  REDUCESCATTER   %s      1       NONE 0        1      NONE   0      1\n' "$(( MSG_BYTES / 2 ))"
                printf 'rs_ag_allgather     -1 1  ALLGATHER   %s      1       NONE 0        1      NONE   0      1\n' "$(( MSG_BYTES / 2 ))"
                ;;
            compute_overlap)
                printf 'compute_overlap_comm0     -1 1000  ALLREDUCE   %s      1       NONE 0        1      NONE   0      1\n' "$(( MSG_BYTES / 2 ))"
                printf 'compute_overlap_comm1     -1 1000  ALLREDUCE   %s      1       NONE 0        1      NONE   0      1\n' "$(( MSG_BYTES / 2 ))"
                ;;
            moe_pipeline)
                printf 'moe_pipeline_dispatch     -1 1000  NONE   0      1       NONE 0        1      ALLTOALL_EP   %s      1\n' "$(( MSG_BYTES / 2 ))"
                printf 'moe_pipeline_combine     -1 1000  NONE   0      1       NONE 0        1      ALLTOALL_EP   %s      1\n' "$(( MSG_BYTES / 2 ))"
                ;;
        esac
    } > "${output}"
}

WORKLOAD_TXT="${OUTPUT_DIR}/workload.txt"
write_simai_workload "${WORKLOAD_TXT}"

ENABLE_CALENDAR=0
if [[ "${MODE}" == "calendar_switch" ]]; then
    ENABLE_CALENDAR=1
fi

TEMPLATE_CONF="${ROOT_DIR}/astra-sim-alibabacloud/inputs/config/SimAI.conf"
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
override_conf_key "TRACE_OUTPUT_FILE" "${OUTPUT_DIR}/trace.tr"
override_conf_key "FCT_OUTPUT_FILE" "${OUTPUT_DIR}/fct.txt"
override_conf_key "PFC_OUTPUT_FILE" "${OUTPUT_DIR}/pfc.txt"
override_conf_key "ENABLE_TRACE" "0"

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
  "moe_phases": ${MOE_PHASE_COUNT},
  "moe_gate_trace_mode": "${MOE_GATE_TRACE_MODE}",
  "moe_gate_trace_file": "${MOE_GATE_TRACE_OUTPUT}",
  "switch_metrics_file": "${OUTPUT_DIR}/calendar_trace.csv.switch_metrics.csv",
  "timestamp": "$(date -Iseconds)"
}
EOF

echo "[run_single] mode=${MODE} granularity=${GRANULARITY} algorithm=${ALGORITHM} gpus=${GPUS} operator=${OPERATOR} msg_bytes=${MSG_BYTES}"
echo "[run_single] workload_json=${OUTPUT_DIR}/workload.json"
echo "[run_single] workload_txt=${WORKLOAD_TXT}"
echo "[run_single] config=${CONF}"
echo "[run_single] output=${OUTPUT_DIR}"

write_empty_e2e_times() {
    printf '[]\n' > "${OUTPUT_DIR}/e2e_times.json"
}

write_run_status() {
    local status="$1"
    local exit_code="$2"
    cat > "${OUTPUT_DIR}/run_status.json" <<EOF
{
  "status": "${status}",
  "exit_code": ${exit_code},
  "timeout_seconds": ${SIM_TIMEOUT_SECONDS}
}
EOF
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
    re.compile(r"all passes finished at time:\s*([0-9]+(?:\.[0-9]+)?)"),
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
TOPOLOGY="${ROOT_DIR}/Spectrum-X_${GPUS}g_8gps_100Gbps_A100"
if "${DRY_RUN}"; then
    echo "[run_single] Dry-run mode: metadata and config written."
    write_empty_e2e_times
    write_run_status "dry_run" 0
elif [[ -x "${SIMULATOR}" ]]; then
    [[ -f "${TOPOLOGY}" ]] || die "Missing topology: ${TOPOLOGY}"
    set +e
    (
        cd "${OUTPUT_DIR}"
        /usr/bin/timeout "${SIM_TIMEOUT_SECONDS}s" env AS_SEND_LAT=3 AS_NVLS_ENABLE=1 "${SIMULATOR}" \
            -t 1 \
            -w "${WORKLOAD_TXT}" \
            -n "${TOPOLOGY}" \
            -c "${CONF}" \
            > "${OUTPUT_DIR}/stdout.log" 2>&1
    )
    sim_exit=$?
    set -e
    if [[ "${sim_exit}" -eq 0 ]]; then
        write_run_status "success" "${sim_exit}"
    elif [[ "${sim_exit}" -eq 124 ]]; then
        echo "[run_single] WARNING: Simulation timed out after ${SIM_TIMEOUT_SECONDS}s" >&2
        write_run_status "timeout" "${sim_exit}"
    else
        echo "[run_single] WARNING: Simulation exited with code ${sim_exit}" >&2
        write_run_status "failed" "${sim_exit}"
    fi
    extract_e2e_times
    echo "[run_single] Simulation complete. Logs in ${OUTPUT_DIR}/stdout.log"
else
    echo "[run_single] WARNING: Simulator binary not found at ${SIMULATOR}"
    echo "[run_single] Dry-run mode: metadata and config written."
    write_empty_e2e_times
    write_run_status "simulator_missing" 127
fi
