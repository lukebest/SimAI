"""
Contract tests for CalendarSwitchNode.

These tests verify that the ns-3 calendar switch wrapper exposes the expected
schedule APIs and keeps the initial implementation within the safe Task 5
boundary: no direct access to SwitchNode private internals.
"""
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HEADER = REPO_ROOT / (
    "ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.h"
)
IMPL = REPO_ROOT / (
    "ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.cc"
)


class TestCalendarSwitchNodeContract:
    def test_header_exists(self):
        assert HEADER.exists(), "calendar-switch-node.h not found"

    def test_extends_switch_node(self):
        code = HEADER.read_text(encoding="utf-8")

        assert re.search(r"class\s+CalendarSwitchNode\s*:\s*public\s+SwitchNode", code)

    def test_declares_lightweight_schedule_types(self):
        code = HEADER.read_text(encoding="utf-8")

        assert "struct CalendarScheduleEntry" in code
        assert re.search(r"std::vector\s*<\s*uint32_t\s*>\s+permutation", code)
        assert re.search(r"uint32_t\s+slots", code)
        assert "struct CalendarSchedule" in code
        assert re.search(
            r"std::vector\s*<\s*CalendarScheduleEntry\s*>\s+entries", code
        )

    def test_has_load_schedule_api(self):
        code = HEADER.read_text(encoding="utf-8")

        assert "LoadSchedule" in code
        assert "slot_ns" in code
        assert "frame_slots" in code

    def test_has_egress_gating_method(self):
        code = HEADER.read_text(encoding="utf-8")

        assert "CalendarAllowEgress" in code

    def test_has_slot_tracking(self):
        code = HEADER.read_text(encoding="utf-8")

        assert "GetCurrentSlotIndex" in code

    def test_impl_uses_simulator_time_for_current_slot(self):
        code = IMPL.read_text(encoding="utf-8")

        assert "Simulator::Now()" in code
        assert "GetNanoSeconds()" in code
        assert re.search(r"/\s*m_slotNs", code)
        assert re.search(r"%\s*m_frameSlots", code)

    def test_load_schedule_enables_only_non_empty_schedule(self):
        code = IMPL.read_text(encoding="utf-8")

        assert "m_schedule = schedule" in code
        assert re.search(r"m_calendarEnabled\s*=\s*!\s*m_schedule\.entries\.empty\(\)", code)

    def test_egress_gating_uses_current_entry_permutation(self):
        code = IMPL.read_text(encoding="utf-8")

        assert "CalendarAllowEgress" in code
        assert re.search(r"permutation\.size\(\)", code)
        assert re.search(r"permutation\s*\[\s*inDev\s*\]\s*==\s*outDev", code)

    def test_baseline_passthrough_when_disabled_or_schedule_empty(self):
        code = IMPL.read_text(encoding="utf-8")

        assert re.search(r"!\s*m_calendarEnabled", code)
        assert re.search(r"m_schedule\.entries\.empty\(\)", code)
        assert "SwitchNode::SwitchReceiveFromDevice" in code

    def test_does_not_copy_private_switch_node_internals(self):
        code = IMPL.read_text(encoding="utf-8")

        for private_member in [
            "m_bytes",
            "m_mmu",
            "m_devices",
            "m_ackHighPrio",
            "CheckAndSendPfc",
            "SwitchSend",
        ]:
            assert private_member not in code
