#!/usr/bin/env bash
# Generate and execute the full calendar-switch experiment matrix.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/results/calendar_study_$(date +%Y%m%d_%H%M%S)"
PARALLEL=1
DRY_RUN=false
SIM_TIMEOUT_SECONDS="${SIM_TIMEOUT_SECONDS:-180}"
SIM_TIMEOUT_EXPLICIT=false
# full: GPU 8+16, all operators, all granularities, all algorithms (default).
# gpu8_mixed: spec 2026-05-09b — GPU=8 only; deterministic ops run RR+BvN+Solstice;
#              dynamic ops run chunk/packet/slot + round_robin only (no demand-aware sweep).
MATRIX="full"
TIME_PROFILE="full"
TOPOLOGY_8_PACKET=""
TOPOLOGY_8_CALENDAR=""
TOPOLOGY_16_PACKET=""
TOPOLOGY_16_CALENDAR=""

usage() {
    cat <<EOF
Usage: $0 [options]
  --parallel N
  --dry-run
  --results-dir DIR
  --sim-timeout-seconds N
  --matrix full|gpu8_mixed
  --time-profile full|quick
  --topology-8-packet PATH
  --topology-8-calendar PATH
  --topology-16-packet PATH
  --topology-16-calendar PATH
EOF
}

die() {
    echo "[run_calendar_study] ERROR: $*" >&2
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
        --parallel) require_value "$1" "${2:-}"; PARALLEL="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --results-dir) require_value "$1" "${2:-}"; RESULTS_DIR="$2"; shift 2 ;;
        --sim-timeout-seconds) require_value "$1" "${2:-}"; SIM_TIMEOUT_SECONDS="$2"; SIM_TIMEOUT_EXPLICIT=true; shift 2 ;;
        --matrix) require_value "$1" "${2:-}"; MATRIX="$2"; shift 2 ;;
        --time-profile) require_value "$1" "${2:-}"; TIME_PROFILE="$2"; shift 2 ;;
        --topology-8-packet) require_value "$1" "${2:-}"; TOPOLOGY_8_PACKET="$2"; shift 2 ;;
        --topology-8-calendar) require_value "$1" "${2:-}"; TOPOLOGY_8_CALENDAR="$2"; shift 2 ;;
        --topology-16-packet) require_value "$1" "${2:-}"; TOPOLOGY_16_PACKET="$2"; shift 2 ;;
        --topology-16-calendar) require_value "$1" "${2:-}"; TOPOLOGY_16_CALENDAR="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

case "${MATRIX}" in
    full|gpu8_mixed) ;;
    *) die "--matrix must be full or gpu8_mixed" ;;
esac

case "${TIME_PROFILE}" in
    full|quick) ;;
    *) die "--time-profile must be full or quick" ;;
esac

if [[ ! "${PARALLEL}" =~ ^[0-9]+$ || "${PARALLEL}" == "0" ]]; then
    die "--parallel must be a positive integer"
fi

mkdir -p "${RESULTS_DIR}"

OPERATORS=(
    "allreduce_ring"
    "allreduce_tree"
    "allgather"
    "reduce_scatter"
    "moe_dispatch"
    "moe_combine"
    "alltoall_ep"
    "rs_ag_fused"
    "compute_overlap"
    "moe_pipeline"
)
# Deterministic vs dynamic per docs/superpowers/specs/2026-05-07-calendar-switch-perf-study-design.md §6
DETERMINISTIC_OPS=(
    "allreduce_ring"
    "allreduce_tree"
    "allgather"
    "reduce_scatter"
    "rs_ag_fused"
    "compute_overlap"
)
DYNAMIC_OPS=(
    "alltoall_ep"
    "moe_dispatch"
    "moe_combine"
    "moe_pipeline"
)
GRANULARITIES=("operator" "phase" "chunk" "packet" "slot")
DYNAMIC_GRANULARITIES=("chunk" "packet" "slot")
ALGORITHMS=("solstice" "bvn" "round_robin")
GPU_COUNTS=(8 16)
MSG_SIZES=(1048576 33554432 268435456)

if [[ "${MATRIX}" == "gpu8_mixed" ]]; then
    GPU_COUNTS=(8)
fi
if [[ "${TIME_PROFILE}" == "quick" ]]; then
    # Quick profile drops the largest 256MB point to shorten turn-around time.
    MSG_SIZES=(1048576 33554432)
fi

RUN_IDX=0
JOBS_FILE="${RESULTS_DIR}/jobs.txt"
: > "${JOBS_FILE}"

append_job() {
    local mode="$1"
    local granularity="$2"
    local algorithm="$3"
    local gpus="$4"
    local operator="$5"
    local msg_bytes="$6"
    local output_dir="$7"
    local topology_file="$8"

    local timeout_budget="${SIM_TIMEOUT_SECONDS}"
    # Adaptive timeout cuts long hangs while preserving headroom for larger payloads.
    if [[ "${SIM_TIMEOUT_EXPLICIT}" != "true" ]]; then
        case "${msg_bytes}" in
            1048576) timeout_budget=120 ;;
            33554432) timeout_budget=360 ;;
            268435456) timeout_budget=900 ;;
            *) timeout_budget="${SIM_TIMEOUT_SECONDS}" ;;
        esac
    fi

    printf 'SIM_TIMEOUT_SECONDS=%q %q --mode %q --granularity %q --algorithm %q --gpus %q --operator %q --msg-bytes %q --output-dir %q --topology-file %q\n' \
        "${timeout_budget}" \
        "${ROOT_DIR}/scripts/run_single_experiment.sh" \
        "${mode}" \
        "${granularity}" \
        "${algorithm}" \
        "${gpus}" \
        "${operator}" \
        "${msg_bytes}" \
        "${output_dir}" \
        "${topology_file}" >> "${JOBS_FILE}"
}

resolve_topology() {
    local gpus="$1"
    local mode="$2"
    case "${gpus}_${mode}" in
        8_packet_switch)
            if [[ -n "${TOPOLOGY_8_PACKET}" ]]; then
                echo "${TOPOLOGY_8_PACKET}"
            else
                echo "topologies/Spectrum-X_8g_8port_packet_no_nvswitch"
            fi
            ;;
        8_calendar_switch)
            if [[ -n "${TOPOLOGY_8_CALENDAR}" ]]; then
                echo "${TOPOLOGY_8_CALENDAR}"
            else
                echo "topologies/Spectrum-X_8g_8port_calendar_no_nvswitch"
            fi
            ;;
        16_packet_switch)
            if [[ -n "${TOPOLOGY_16_PACKET}" ]]; then
                echo "${TOPOLOGY_16_PACKET}"
            else
                echo "topologies/Spectrum-X_16g_16port_packet_no_nvswitch"
            fi
            ;;
        16_calendar_switch)
            if [[ -n "${TOPOLOGY_16_CALENDAR}" ]]; then
                echo "${TOPOLOGY_16_CALENDAR}"
            else
                echo "topologies/Spectrum-X_16g_16port_calendar_no_nvswitch"
            fi
            ;;
        *)
            die "Unsupported topology mapping for gpus=${gpus} mode=${mode}"
            ;;
    esac
}

# Baseline packet-switch runs: one per operator/GPU-count/message-size.
for op in "${OPERATORS[@]}"; do
    for gpus in "${GPU_COUNTS[@]}"; do
        for size in "${MSG_SIZES[@]}"; do
            RUN_IDX=$((RUN_IDX + 1))
            out="${RESULTS_DIR}/baseline/${op}_g${gpus}_s${size}"
            topo="$(resolve_topology "${gpus}" "packet_switch")"
            append_job "packet_switch" "operator" "solstice" "${gpus}" "${op}" "${size}" "${out}" "${topo}"
        done
    done
done

# Calendar-switch runs across all requested dimensions.
if [[ "${MATRIX}" == "full" ]]; then
    for op in "${OPERATORS[@]}"; do
        for gran in "${GRANULARITIES[@]}"; do
            for algo in "${ALGORITHMS[@]}"; do
                for gpus in "${GPU_COUNTS[@]}"; do
                    for size in "${MSG_SIZES[@]}"; do
                        RUN_IDX=$((RUN_IDX + 1))
                        out="${RESULTS_DIR}/calendar/${op}_${gran}_${algo}_g${gpus}_s${size}"
                        topo="$(resolve_topology "${gpus}" "calendar_switch")"
                        append_job "calendar_switch" "${gran}" "${algo}" "${gpus}" "${op}" "${size}" "${out}" "${topo}"
                    done
                done
            done
        done
    done
else
    # gpu8_mixed: deterministic — all granularities × all algorithms; dynamic — 3 grans × RR only
    for op in "${DETERMINISTIC_OPS[@]}"; do
        for gran in "${GRANULARITIES[@]}"; do
            for algo in "${ALGORITHMS[@]}"; do
                for gpus in "${GPU_COUNTS[@]}"; do
                    for size in "${MSG_SIZES[@]}"; do
                        RUN_IDX=$((RUN_IDX + 1))
                        out="${RESULTS_DIR}/calendar/${op}_${gran}_${algo}_g${gpus}_s${size}"
                        topo="$(resolve_topology "${gpus}" "calendar_switch")"
                        append_job "calendar_switch" "${gran}" "${algo}" "${gpus}" "${op}" "${size}" "${out}" "${topo}"
                    done
                done
            done
        done
    done
    for op in "${DYNAMIC_OPS[@]}"; do
        for gran in "${DYNAMIC_GRANULARITIES[@]}"; do
            for gpus in "${GPU_COUNTS[@]}"; do
                for size in "${MSG_SIZES[@]}"; do
                    RUN_IDX=$((RUN_IDX + 1))
                    out="${RESULTS_DIR}/calendar/${op}_${gran}_round_robin_g${gpus}_s${size}"
                    topo="$(resolve_topology "${gpus}" "calendar_switch")"
                    append_job "calendar_switch" "${gran}" "round_robin" "${gpus}" "${op}" "${size}" "${out}" "${topo}"
                done
            done
        done
    done
fi

echo "Total runs: ${RUN_IDX}"
echo "Jobs file: ${JOBS_FILE}"
echo "Results dir: ${RESULTS_DIR}"

if "${DRY_RUN}"; then
    echo "[DRY-RUN] Would execute ${RUN_IDX} runs with parallelism ${PARALLEL}"
    sed -n '1,5p' "${JOBS_FILE}"
    echo "..."
    exit 0
fi

for gpus in "${GPU_COUNTS[@]}"; do
    for mode in packet_switch calendar_switch; do
        topo_rel="$(resolve_topology "${gpus}" "${mode}")"
        topo_abs="${ROOT_DIR}/${topo_rel}"
        [[ -f "${topo_abs}" ]] || die "Missing topology: ${topo_abs}"
    done
done

if command -v parallel >/dev/null 2>&1; then
    parallel --halt never -j "${PARALLEL}" < "${JOBS_FILE}" || true
else
    running=0
    failed=0
    while IFS= read -r cmd; do
        bash -lc "${cmd}" &
        running=$((running + 1))
        if [[ "${running}" -ge "${PARALLEL}" ]]; then
            if ! wait -n; then
                failed=$((failed + 1))
            fi
            running=$((running - 1))
        fi
    done < "${JOBS_FILE}"
    while [[ "${running}" -gt 0 ]]; do
        if ! wait -n; then
            failed=$((failed + 1))
        fi
        running=$((running - 1))
    done
    if [[ "${failed}" -gt 0 ]]; then
        echo "[WARN] ${failed} jobs exited non-zero; sweep continued." >&2
    fi
fi

echo "[DONE] All ${RUN_IDX} runs completed."
