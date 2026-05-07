"""
Contract tests for the calendar switch granularity controller.
"""
import re
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HEADER = REPO_ROOT / (
    "astra-sim-alibabacloud/astra-sim/network_frontend/ns3/"
    "granularity_controller.h"
)
ENTRY_H = REPO_ROOT / "astra-sim-alibabacloud/astra-sim/network_frontend/ns3/entry.h"


class TestGranularityControllerContract:
    def test_header_exists(self):
        assert HEADER.exists(), "granularity_controller.h not found"

    def test_declares_modes_and_parser_mappings(self):
        code = HEADER.read_text(encoding="utf-8")

        assert re.search(r"enum\s+class\s+GranularityMode\s*\{[^}]*OPERATOR", code)
        for mode in ["PHASE", "CHUNK", "PACKET", "SLOT"]:
            assert mode in code

        for alias in [
            "operator",
            "phase",
            "stage",
            "chunk",
            "tile",
            "packet",
            "slot",
            "cycle",
        ]:
            assert f'"{alias}"' in code

    def test_declares_required_controller_apis(self):
        code = HEADER.read_text(encoding="utf-8")

        assert "class GranularityController" in code
        assert "BuildDemandMatrix" in code
        assert "ShouldReschedule" in code
        assert "OnFlowStart" in code
        assert "Reset" in code

    def test_header_api_compiles_and_matches_required_behavior(self, tmp_path):
        source = tmp_path / "granularity_controller_smoke.cc"
        binary = tmp_path / "granularity_controller_smoke"
        source.write_text(
            textwrap.dedent(
                """
                #include <cstdint>
                #include <iostream>

                #include "granularity_controller.h"

                struct FlowTag {
                  int tag_id;
                  int current_flow_id;
                  int chunk_id;
                };

                int main() {
                  using calendar::GranularityController;
                  using calendar::GranularityMode;

                  if (calendar::ParseGranularityMode("operator") !=
                      GranularityMode::OPERATOR) {
                    return 1;
                  }
                  if (calendar::ParseGranularityMode("stage") !=
                      GranularityMode::PHASE) {
                    return 2;
                  }
                  if (calendar::ParseGranularityMode("tile") !=
                      GranularityMode::CHUNK) {
                    return 3;
                  }
                  if (calendar::ParseGranularityMode("packet") !=
                      GranularityMode::PACKET) {
                    return 4;
                  }
                  if (calendar::ParseGranularityMode("cycle") !=
                      GranularityMode::SLOT) {
                    return 5;
                  }

                  GranularityController controller(GranularityMode::CHUNK, 3);
                  controller.OnFlowStart(0, 1, 128, FlowTag{10, 20, 1});
                  controller.OnFlowStart(0, 1, 64, FlowTag{10, 20, 1});
                  controller.OnFlowStart(-1, 1, 999, FlowTag{10, 20, 1});
                  controller.OnFlowStart(1, 3, 999, FlowTag{10, 20, 1});
                  const auto demand = controller.BuildDemandMatrix();
                  if (demand.size() != 3 || demand[0].size() != 3) {
                    return 6;
                  }
                  if (demand[0][1] != 192.0) {
                    return 7;
                  }
                  if (controller.BuildDemandMatrix()[0][1] != 0.0) {
                    return 8;
                  }

                  if (!controller.ShouldReschedule(FlowTag{10, 20, 1})) {
                    return 9;
                  }
                  if (controller.ShouldReschedule(FlowTag{10, 20, 1})) {
                    return 10;
                  }
                  if (!controller.ShouldReschedule(FlowTag{10, 20, 2})) {
                    return 11;
                  }

                  GranularityController packet(GranularityMode::PACKET, 2);
                  if (!packet.ShouldReschedule(FlowTag{1, 1, 1}) ||
                      !packet.ShouldReschedule(nullptr)) {
                    return 12;
                  }

                  GranularityController slot(GranularityMode::SLOT, 2);
                  if (slot.ShouldReschedule(FlowTag{1, 1, 1})) {
                    return 13;
                  }

                  controller.Reset();
                  if (!controller.ShouldReschedule(FlowTag{10, 20, 1})) {
                    return 14;
                  }
                  return 0;
                }
                """
            ),
            encoding="utf-8",
        )

        compile_result = subprocess.run(
            [
                "c++",
                "-std=c++17",
                "-I",
                str(HEADER.parent),
                str(source),
                "-o",
                str(binary),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert compile_result.returncode == 0, compile_result.stderr

        run_result = subprocess.run(
            [str(binary)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert run_result.returncode == 0, run_result.stderr

    def test_entry_h_includes_and_exposes_controller(self):
        code = ENTRY_H.read_text(encoding="utf-8")

        assert '#include "granularity_controller.h"' in code
        assert re.search(
            r"std::unique_ptr\s*<\s*calendar::GranularityController\s*>\s+"
            r"g_granularity_controller",
            code,
        )

    def test_send_flow_wires_controller_under_calendar_switch_flag(self):
        code = ENTRY_H.read_text(encoding="utf-8")
        start = code.find("void SendFlow(")
        end = code.find("void notify_receiver_receive_data", start)

        assert start != -1
        assert end != -1
        body = code[start:end]
        assert "enable_calendar_switch" in body
        assert "g_granularity_controller" in body
        assert "OnFlowStart" in body
        assert "ShouldReschedule" in body
        assert "BuildDemandMatrix" in body
