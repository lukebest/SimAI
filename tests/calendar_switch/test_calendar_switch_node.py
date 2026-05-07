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
SWITCH_NODE = REPO_ROOT / (
    "ns-3-alibabacloud/simulation/src/point-to-point/model/switch-node.h"
)
SWITCH_NODE_IMPL = REPO_ROOT / (
    "ns-3-alibabacloud/simulation/src/point-to-point/model/switch-node.cc"
)
ENTRY = REPO_ROOT / (
    "astra-sim-alibabacloud/astra-sim/network_frontend/ns3/entry.h"
)
GRANULARITY_CONTROLLER = REPO_ROOT / (
    "astra-sim-alibabacloud/astra-sim/network_frontend/ns3/granularity_controller.h"
)
CMAKE_LISTS = REPO_ROOT / (
    "ns-3-alibabacloud/simulation/src/point-to-point/CMakeLists.txt"
)


class TestCalendarSwitchNodeContract:
    def test_header_exists(self):
        assert HEADER.exists(), "calendar-switch-node.h not found"

    def test_point_to_point_build_registers_calendar_switch_node(self):
        cmake = CMAKE_LISTS.read_text(encoding="utf-8")

        source_files = re.search(
            r"SOURCE_FILES(?P<body>.*?)HEADER_FILES", cmake, re.DOTALL
        )
        header_files = re.search(
            r"HEADER_FILES(?P<body>.*?)LIBRARIES_TO_LINK", cmake, re.DOTALL
        )

        assert source_files is not None, "point-to-point CMake missing SOURCE_FILES"
        assert header_files is not None, "point-to-point CMake missing HEADER_FILES"
        assert "model/calendar-switch-node.cc" in source_files.group("body")
        assert "model/calendar-switch-node.h" in header_files.group("body")

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

    def test_switch_node_delegation_hooks_are_virtual(self):
        code = SWITCH_NODE.read_text(encoding="utf-8")

        protected_section = re.search(r"protected:(?P<body>.*?)private:", code, re.DOTALL)
        assert protected_section is not None, "SwitchNode missing protected section"
        protected = protected_section.group("body")
        assert re.search(
            r"virtual\s+void\s+SendToDev\s*\(\s*Ptr\s*<\s*Packet\s*>\s*p\s*,"
            r"\s*CustomHeader\s*&\s*ch\s*\)",
            protected,
        )
        assert re.search(
            r"int\s+GetOutDev\s*\(\s*Ptr\s*<\s*const\s+Packet\s*>\s*,"
            r"\s*CustomHeader\s*&\s*ch\s*\)",
            protected,
        )
        assert re.search(
            r"virtual\s+bool\s+SwitchReceiveFromDevice\s*\("
            r"\s*Ptr\s*<\s*NetDevice\s*>\s+device,\s*"
            r"Ptr\s*<\s*Packet\s*>\s+packet,\s*CustomHeader\s*&\s*ch\s*\)",
            code,
            re.MULTILINE,
        )
        assert re.search(
            r"virtual\s+void\s+SwitchNotifyDequeue\s*\("
            r"\s*uint32_t\s+ifIndex,\s*uint32_t\s+qIndex,\s*"
            r"Ptr\s*<\s*Packet\s*>\s+p\s*\)",
            code,
            re.MULTILINE,
        )

    def test_calendar_switch_marks_delegation_hooks_override(self):
        code = HEADER.read_text(encoding="utf-8")

        assert re.search(
            r"void\s+SendToDev\s*\(\s*Ptr\s*<\s*Packet\s*>\s*p\s*,"
            r"\s*CustomHeader\s*&\s*ch\s*\)\s+override\s*;",
            code,
        )
        assert re.search(
            r"bool\s+SwitchReceiveFromDevice\s*\([^;]*CustomHeader\s*&\s*ch\s*\)"
            r"\s+override\s*;",
            code,
            re.DOTALL,
        )
        assert re.search(
            r"void\s+SwitchNotifyDequeue\s*\([^;]*Ptr\s*<\s*Packet\s*>\s+p\s*\)"
            r"\s+override\s*;",
            code,
            re.DOTALL,
        )

    def test_impl_uses_simulator_time_for_current_slot(self):
        code = IMPL.read_text(encoding="utf-8")

        assert "Simulator::Now()" in code
        assert "GetNanoSeconds()" in code
        assert re.search(r"/\s*m_slotNs", code)
        assert re.search(r"%\s*m_frameSlots", code)

    def test_load_schedule_enables_only_non_empty_schedule(self):
        code = IMPL.read_text(encoding="utf-8")

        assert re.search(r"m_calendarEnabled\s*=\s*false", code)
        assert re.search(r"m_schedule\.entries\.clear\(\)", code)
        assert re.search(r"m_calendarEnabled\s*=\s*true", code)

    def test_load_schedule_rejects_invalid_timing_parameters(self):
        code = IMPL.read_text(encoding="utf-8")

        assert re.search(r"slot_ns\s*==\s*0", code)
        assert re.search(r"frame_slots\s*==\s*0", code)
        invalid_timing_guard = re.search(
            r"if\s*\((?P<condition>[^\n]+)\)\s*\{\s*return\s*;", code
        )

        assert invalid_timing_guard is not None
        assert "slot_ns == 0" in invalid_timing_guard.group("condition")
        assert "frame_slots == 0" in invalid_timing_guard.group("condition")

    def test_load_schedule_filters_zero_slot_entries_and_requires_exact_frame(self):
        code = IMPL.read_text(encoding="utf-8")

        assert re.search(r"entry\.slots\s*==\s*0", code)
        assert re.search(r"continue\s*;", code)
        assert "totalSlots" in code
        assert re.search(r"totalSlots\s*!=\s*m_frameSlots", code)
        invalid_total_guard = re.search(
            r"if\s*\((?P<condition>[^\n]*totalSlots\s*!=\s*m_frameSlots[^\n]*)\)"
            r"\s*\{\s*m_schedule\.entries\.clear\(\);\s*return\s*;",
            code,
        )

        assert invalid_total_guard is not None

    def test_get_current_entry_returns_null_for_uncovered_slots(self):
        code = IMPL.read_text(encoding="utf-8")
        get_current_entry = re.search(
            r"const\s+CalendarScheduleEntry\s*\*\s*"
            r"CalendarSwitchNode::GetCurrentEntry\s*\([^)]*\)\s*const\s*\{(?P<body>.*?)\n\}",
            code,
            re.DOTALL,
        )

        assert get_current_entry is not None
        body = get_current_entry.group("body")
        assert "m_schedule.entries.back()" not in body
        assert re.search(r"return\s+nullptr\s*;", body)

    def test_egress_gating_uses_current_entry_permutation(self):
        code = IMPL.read_text(encoding="utf-8")

        assert "CalendarAllowEgress" in code
        assert re.search(r"permutation\.size\(\)", code)
        assert re.search(r"permutation\s*\[\s*inDev\s*\]\s*==\s*outDev", code)

    def test_baseline_passthrough_when_disabled_or_schedule_empty(self):
        code = IMPL.read_text(encoding="utf-8")

        assert re.search(r"!\s*m_calendarEnabled", code)
        assert re.search(r"m_schedule\.entries\.empty\(\)", code)
        assert "SwitchNode::SendToDev" in code

    def test_forwarding_path_checks_calendar_gate(self):
        code = IMPL.read_text(encoding="utf-8")
        send_to_dev = re.search(
            r"void\s+CalendarSwitchNode::SendToDev\s*\([^)]*CustomHeader\s*&\s*ch\s*\)"
            r"\s*\{(?P<body>.*?)\n\}",
            code,
            re.DOTALL,
        )

        assert send_to_dev is not None
        body = send_to_dev.group("body")
        assert "GetOutDev" in body
        assert "FlowIdTag" in body
        assert "CalendarAllowEgress" in body
        assert "SwitchNode::SendToDev" in body

    def test_blocked_forwarding_retries_at_next_slot(self):
        code = IMPL.read_text(encoding="utf-8")
        send_to_dev = re.search(
            r"void\s+CalendarSwitchNode::SendToDev\s*\([^)]*CustomHeader\s*&\s*ch\s*\)"
            r"\s*\{(?P<body>.*?)\n\}",
            code,
            re.DOTALL,
        )

        assert send_to_dev is not None
        body = send_to_dev.group("body")
        assert re.search(r"!\s*CalendarAllowEgress\s*\(", body)
        assert "Simulator::Schedule" in body
        assert "GetNanoSeconds" in body
        assert "m_slotNs" in body
        assert re.search(r"&CalendarSwitchNode::SendToDev", body)

    def test_switch_receive_delegates_to_virtual_send_to_dev(self):
        code = SWITCH_NODE_IMPL.read_text(encoding="utf-8")
        switch_receive = re.search(
            r"bool\s+SwitchNode::SwitchReceiveFromDevice\s*\([^)]*CustomHeader\s*&\s*ch\s*\)"
            r"\s*\{(?P<body>.*?)\n\}",
            code,
            re.DOTALL,
        )

        assert switch_receive is not None
        assert re.search(r"SendToDev\s*\(\s*packet\s*,\s*ch\s*\)", switch_receive.group("body"))

    def test_entry_builds_and_loads_calendar_schedule(self):
        code = ENTRY.read_text(encoding="utf-8")

        assert re.search(r"auto\s+demand\s*=\s*g_granularity_controller->BuildDemandMatrix\(\)", code)
        assert "BuildCalendarSchedule" in code
        assert "CalendarSwitchNode" in code
        assert "DynamicCast<CalendarSwitchNode>" in code
        assert "LoadSchedule" in code
        assert "calendar_slot_ns" in code
        assert "calendar_frame_slots" in code

    def test_entry_uses_calendar_algorithm_for_schedule_generation(self):
        code = ENTRY.read_text(encoding="utf-8")

        schedule_call = re.search(
            r"BuildCalendarSchedule\s*\((?P<args>[^;]+)\)",
            code,
            re.DOTALL,
        )
        assert schedule_call is not None
        assert "calendar_algorithm" in schedule_call.group("args")

    def test_granularity_controller_has_header_only_scheduler(self):
        code = GRANULARITY_CONTROLLER.read_text(encoding="utf-8")

        assert "BuildCalendarSchedule" in code
        assert "round_robin" in code
        assert "demand" in code
        assert "CalendarSchedule" in code

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
