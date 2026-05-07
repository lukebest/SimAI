"""
Tests for calendar-study workload generation.

These tests lock down the Task 8 output schemas for collective, MoE, and
fused operator workloads without depending on the later experiment runner.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKLOAD_DIR = REPO_ROOT / "workloads" / "calendar_study"
sys.path.insert(0, str(WORKLOAD_DIR))

from fused_op_workloads import generate_moe_pipeline, generate_rs_ag_fused  # noqa: E402
from generate_workloads import OPERATOR_CONFIGS, generate_collective_workload  # noqa: E402
from moe_traffic_generator import generate_moe_demand_matrix  # noqa: E402


def _as_array(phase):
    return np.asarray(phase["demand_matrix"])


def _assert_square_zero_diagonal(matrix, num_gpus):
    assert matrix.shape == (num_gpus, num_gpus)
    assert np.all(np.diag(matrix) == 0)


class TestCollectiveWorkloadGeneration:
    @pytest.mark.parametrize(
        ("operator", "expected_phases"),
        [
            ("allreduce_ring", 7),
            ("allgather", 7),
            ("reduce_scatter", 7),
            ("allreduce_tree", 2),
        ],
    )
    def test_collective_workload_schema_and_phase_count(
        self, operator, expected_phases
    ):
        wl = generate_collective_workload(
            operator, num_gpus=8, msg_bytes=32 * 1024 * 1024
        )

        assert operator in OPERATOR_CONFIGS
        assert wl["operator"] == operator
        assert wl["num_gpus"] == 8
        assert wl["msg_bytes"] == 32 * 1024 * 1024
        assert wl["num_phases"] == expected_phases
        assert len(wl["phases"]) == expected_phases

        for phase in wl["phases"]:
            _assert_square_zero_diagonal(_as_array(phase), 8)

    @pytest.mark.parametrize(
        "operator", ["allreduce_ring", "allgather", "reduce_scatter"]
    )
    def test_ring_phases_represent_neighbor_traffic(self, operator):
        wl = generate_collective_workload(operator, num_gpus=4, msg_bytes=1024)

        for phase in wl["phases"]:
            matrix = _as_array(phase)
            _assert_square_zero_diagonal(matrix, 4)
            for src in range(4):
                dst = (src + 1) % 4
                assert matrix[src, dst] > 0
                assert np.count_nonzero(matrix[src]) == 1

    def test_tree_reduce_and_broadcast_are_binary_tree_demands(self):
        wl = generate_collective_workload(
            "allreduce_tree", num_gpus=8, msg_bytes=1024
        )

        assert [phase["name"] for phase in wl["phases"]] == ["reduce", "broadcast"]
        reduce_dm = _as_array(wl["phases"][0])
        broadcast_dm = _as_array(wl["phases"][1])
        _assert_square_zero_diagonal(reduce_dm, 8)
        _assert_square_zero_diagonal(broadcast_dm, 8)
        assert reduce_dm.sum() > 0
        assert broadcast_dm.sum() > 0
        assert np.all((reduce_dm > 0) == (broadcast_dm.T > 0))


class TestMoETrafficGeneration:
    def test_uniform_distribution_returns_demand_matrix(self):
        dm = generate_moe_demand_matrix(
            num_gpus=8,
            num_experts=64,
            tokens_per_gpu=512,
            token_size=4096,
            distribution="uniform",
        )

        assert dm.shape == (8, 8)
        assert dm.sum() == 8 * 512 * 4096

    def test_zipf_and_power_law_are_more_skewed_than_uniform(self):
        kwargs = dict(
            num_gpus=8,
            num_experts=64,
            tokens_per_gpu=512,
            token_size=4096,
            zipf_s=1.5,
            seed=7,
        )

        uniform = generate_moe_demand_matrix(distribution="uniform", **kwargs)
        zipf = generate_moe_demand_matrix(distribution="zipf", **kwargs)
        power_law = generate_moe_demand_matrix(distribution="power_law", **kwargs)

        assert zipf.std() > uniform.std()
        assert power_law.std() > uniform.std()

    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(num_gpus=0, num_experts=8, tokens_per_gpu=1, token_size=1),
            dict(num_gpus=4, num_experts=0, tokens_per_gpu=1, token_size=1),
            dict(num_gpus=4, num_experts=8, tokens_per_gpu=0, token_size=1),
            dict(num_gpus=4, num_experts=8, tokens_per_gpu=1, token_size=0),
            dict(num_gpus=8, num_experts=4, tokens_per_gpu=1, token_size=1),
        ],
    )
    def test_moe_validates_positive_inputs_and_expert_count(self, kwargs):
        with pytest.raises(ValueError):
            generate_moe_demand_matrix(**kwargs)

    def test_moe_rejects_invalid_distribution(self):
        with pytest.raises(ValueError, match="Unknown distribution"):
            generate_moe_demand_matrix(
                num_gpus=4,
                num_experts=8,
                tokens_per_gpu=16,
                token_size=32,
                distribution="not_real",
            )


class TestFusedWorkloads:
    def test_rs_ag_fused_uses_two_high_level_phases(self):
        wl = generate_rs_ag_fused(num_gpus=8, msg_bytes=32 * 1024 * 1024)

        assert wl["operator"] == "rs_ag_fused"
        assert wl["num_gpus"] == 8
        assert wl["msg_bytes"] == 32 * 1024 * 1024
        assert wl["num_phases"] == 2
        assert len(wl["phases"]) == 2
        assert [phase["name"] for phase in wl["phases"]] == [
            "reduce_scatter",
            "allgather",
        ]
        for phase in wl["phases"]:
            _assert_square_zero_diagonal(_as_array(phase), 8)

    def test_moe_pipeline_has_dispatch_compute_and_combine(self):
        wl = generate_moe_pipeline(
            num_gpus=8,
            num_experts=64,
            tokens_per_gpu=512,
            token_size=4096,
            distribution="uniform",
            compute_ns=12345,
        )

        assert wl["operator"] == "moe_pipeline"
        assert wl["num_phases"] == 3
        assert [phase["name"] for phase in wl["phases"]] == [
            "dispatch",
            "expert_compute",
            "combine",
        ]

        dispatch = _as_array(wl["phases"][0])
        compute = _as_array(wl["phases"][1])
        combine = _as_array(wl["phases"][2])
        assert dispatch.sum() == 8 * 512 * 4096
        assert np.all(compute == 0)
        assert wl["phases"][1]["compute_ns"] == 12345
        assert np.array_equal(combine, dispatch.T)


def test_workload_modules_import_as_repo_packages():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import workloads.calendar_study.fused_op_workloads",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr


def test_generate_workloads_cli_writes_json(tmp_path):
    output_path = tmp_path / "allgather.json"

    subprocess.run(
        [
            sys.executable,
            str(WORKLOAD_DIR / "generate_workloads.py"),
            "--operator",
            "allgather",
            "--num-gpus",
            "4",
            "--msg-bytes",
            "1024",
            "--output",
            str(output_path),
        ],
        check=True,
        cwd=REPO_ROOT,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["operator"] == "allgather"
    assert payload["num_phases"] == 3
    assert len(payload["phases"]) == 3
