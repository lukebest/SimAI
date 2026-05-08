#!/usr/bin/env bash
# Generate and execute the full calendar-switch experiment matrix.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/results/calendar_study_$(date +%Y%m%d_%H%M%S)"
PARALLEL=1
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $0 [options]
  --parallel N
  --dry-run
  --results-dir DIR
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
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

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
GRANULARITIES=("operator" "phase" "chunk" "packet" "slot")
ALGORITHMS=("solstice" "bvn" "round_robin")
GPU_COUNTS=(8 16)
MSG_SIZES=(1048576 33554432 268435456)

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

    printf '%q --mode %q --granularity %q --algorithm %q --gpus %q --operator %q --msg-bytes %q --output-dir %q\n' \
        "${ROOT_DIR}/scripts/run_single_experiment.sh" \
        "${mode}" \
        "${granularity}" \
        "${algorithm}" \
        "${gpus}" \
        "${operator}" \
        "${msg_bytes}" \
        "${output_dir}" >> "${JOBS_FILE}"
}

# Baseline packet-switch runs: one per operator/GPU-count/message-size.
for op in "${OPERATORS[@]}"; do
    for gpus in "${GPU_COUNTS[@]}"; do
        for size in "${MSG_SIZES[@]}"; do
            RUN_IDX=$((RUN_IDX + 1))
            out="${RESULTS_DIR}/baseline/${op}_g${gpus}_s${size}"
            append_job "packet_switch" "operator" "solstice" "${gpus}" "${op}" "${size}" "${out}"
        done
    done
done

# Calendar-switch runs across all requested dimensions.
for op in "${OPERATORS[@]}"; do
    for gran in "${GRANULARITIES[@]}"; do
        for algo in "${ALGORITHMS[@]}"; do
            for gpus in "${GPU_COUNTS[@]}"; do
                for size in "${MSG_SIZES[@]}"; do
                    RUN_IDX=$((RUN_IDX + 1))
                    out="${RESULTS_DIR}/calendar/${op}_${gran}_${algo}_g${gpus}_s${size}"
                    append_job "calendar_switch" "${gran}" "${algo}" "${gpus}" "${op}" "${size}" "${out}"
                done
            done
        done
    done
done

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
    topo="${ROOT_DIR}/Spectrum-X_${gpus}g_8gps_100Gbps_A100"
    if [[ ! -f "${topo}" ]]; then
        python3 "${ROOT_DIR}/astra-sim-alibabacloud/inputs/topo/gen_Topo_Template.py" \
            -topo Spectrum-X \
            -g "${gpus}" \
            -gt A100 \
            -bw 100Gbps \
            -nvbw 2400Gbps
    fi
done

if command -v parallel >/dev/null 2>&1; then
    parallel -j "${PARALLEL}" < "${JOBS_FILE}"
else
    running=0
    while IFS= read -r cmd; do
        bash -lc "${cmd}" &
        running=$((running + 1))
        if [[ "${running}" -ge "${PARALLEL}" ]]; then
            wait -n
            running=$((running - 1))
        fi
    done < "${JOBS_FILE}"
    wait
fi

echo "[DONE] All ${RUN_IDX} runs completed."
