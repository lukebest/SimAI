"""
Baseline parity contract tests for CalendarSwitchNode.

These tests are intentionally source-level: they verify that calendar switching
is opt-in and that the default/disabled path keeps dispatching through the
baseline SwitchNode behavior.
"""
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CALENDAR_HEADER = REPO_ROOT / (
    "ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.h"
)
CALENDAR_IMPL = REPO_ROOT / (
    "ns-3-alibabacloud/simulation/src/point-to-point/model/calendar-switch-node.cc"
)
SWITCH_HEADER = REPO_ROOT / (
    "ns-3-alibabacloud/simulation/src/point-to-point/model/switch-node.h"
)
COMMON_H = REPO_ROOT / (
    "astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h"
)


def read_text(path):
    return path.read_text(encoding="utf-8")


def function_body(code, qualified_name):
    match = re.search(rf"{re.escape(qualified_name)}\s*\([^)]*\)\s*(?:const\s*)?\{{", code)
    assert match is not None, f"missing function body for {qualified_name}"

    body_start = match.end()
    depth = 1
    pos = body_start
    while pos < len(code) and depth:
        if code[pos] == "{":
            depth += 1
        elif code[pos] == "}":
            depth -= 1
        pos += 1

    assert depth == 0, f"unterminated function body for {qualified_name}"
    return code[body_start : pos - 1]


def node_type_one_branch(code):
    match = re.search(
        r"else\s*if\s*\(\s*node_type\[i\]\s*==\s*1\s*\)\s*\{",
        code,
    )
    assert match is not None, "common.h missing switch-node topology branch"

    body_start = match.end()
    depth = 1
    pos = body_start
    while pos < len(code) and depth:
        if code[pos] == "{":
            depth += 1
        elif code[pos] == "}":
            depth -= 1
        pos += 1

    assert depth == 0, "unterminated switch-node topology branch"
    return code[body_start : pos - 1]


class TestBaselineParityContract:
    def test_default_config_disables_calendar_switch(self):
        code = read_text(COMMON_H)

        assert re.search(r"uint32_t\s+enable_calendar_switch\s*=\s*0\s*;", code)

    def test_disabled_receive_path_delegates_to_switch_node(self):
        body = function_body(read_text(CALENDAR_IMPL), "CalendarSwitchNode::SwitchReceiveFromDevice")

        disabled_guard = re.search(
            r"if\s*\(\s*!\s*m_calendarEnabled\s*\|\|\s*"
            r"m_schedule\.entries\.empty\(\)\s*\)\s*\{(?P<body>.*?)\}",
            body,
            re.DOTALL,
        )
        assert disabled_guard is not None
        assert re.search(
            r"return\s+SwitchNode::SwitchReceiveFromDevice\s*\("
            r"\s*device\s*,\s*packet\s*,\s*ch\s*\)\s*;",
            disabled_guard.group("body"),
        )

    def test_dequeue_notification_delegates_to_switch_node(self):
        body = function_body(read_text(CALENDAR_IMPL), "CalendarSwitchNode::SwitchNotifyDequeue")

        assert re.search(
            r"SwitchNode::SwitchNotifyDequeue\s*\("
            r"\s*ifIndex\s*,\s*qIndex\s*,\s*p\s*\)\s*;",
            body,
        )

    def test_topology_uses_plain_switch_node_when_calendar_disabled(self):
        branch = node_type_one_branch(read_text(COMMON_H))

        disabled_branch = re.search(
            r"else\s*\{(?P<body>.*?)\}\s*$",
            branch,
            re.DOTALL,
        )
        assert disabled_branch is not None
        assert re.search(
            r"Ptr\s*<\s*SwitchNode\s*>\s+sw\s*=\s*"
            r"CreateObject\s*<\s*SwitchNode\s*>\s*\(\s*\)\s*;",
            disabled_branch.group("body"),
        )
        assert "CreateObject<CalendarSwitchNode>" not in disabled_branch.group("body")

    def test_topology_uses_calendar_switch_node_only_when_enabled(self):
        branch = node_type_one_branch(read_text(COMMON_H))

        enabled_branch = re.search(
            r"if\s*\(\s*enable_calendar_switch\s*\)\s*\{(?P<body>.*?)\}"
            r"\s*else\s*\{",
            branch,
            re.DOTALL,
        )
        assert enabled_branch is not None
        assert re.search(
            r"Ptr\s*<\s*CalendarSwitchNode\s*>\s+sw\s*=\s*"
            r"CreateObject\s*<\s*CalendarSwitchNode\s*>\s*\(\s*\)\s*;",
            enabled_branch.group("body"),
        )

    def test_parent_methods_are_virtual_and_calendar_methods_override(self):
        switch_header = read_text(SWITCH_HEADER)
        calendar_header = read_text(CALENDAR_HEADER)

        assert re.search(
            r"virtual\s+bool\s+SwitchReceiveFromDevice\s*\("
            r"\s*Ptr\s*<\s*NetDevice\s*>\s+device,\s*"
            r"Ptr\s*<\s*Packet\s*>\s+packet,\s*CustomHeader\s*&\s*ch\s*\)",
            switch_header,
        )
        assert re.search(
            r"virtual\s+void\s+SwitchNotifyDequeue\s*\("
            r"\s*uint32_t\s+ifIndex,\s*uint32_t\s+qIndex,\s*"
            r"Ptr\s*<\s*Packet\s*>\s+p\s*\)",
            switch_header,
        )
        assert re.search(
            r"bool\s+SwitchReceiveFromDevice\s*\([^;]*CustomHeader\s*&\s*ch\s*\)"
            r"\s+override\s*;",
            calendar_header,
            re.DOTALL,
        )
        assert re.search(
            r"void\s+SwitchNotifyDequeue\s*\([^;]*Ptr\s*<\s*Packet\s*>\s+p\s*\)"
            r"\s+override\s*;",
            calendar_header,
            re.DOTALL,
        )

    def test_invalid_or_empty_schedule_never_enables_calendar_behavior(self):
        code = read_text(CALENDAR_IMPL)
        load_body = function_body(code, "CalendarSwitchNode::LoadSchedule")
        egress_body = function_body(code, "CalendarSwitchNode::CalendarAllowEgress")

        assert re.search(r"m_calendarEnabled\s*=\s*false\s*;", load_body)
        assert re.search(r"m_schedule\.entries\.clear\(\)\s*;", load_body)
        assert re.search(
            r"if\s*\(\s*schedule\.entries\.empty\(\)\s*\|\|\s*slot_ns\s*==\s*0"
            r"\s*\|\|\s*frame_slots\s*==\s*0\s*\)\s*\{\s*return\s*;",
            load_body,
            re.DOTALL,
        )
        assert re.search(
            r"if\s*\(\s*m_schedule\.entries\.empty\(\)\s*\|\|\s*"
            r"totalSlots\s*!=\s*m_frameSlots\s*\)\s*\{\s*"
            r"m_schedule\.entries\.clear\(\)\s*;\s*return\s*;",
            load_body,
            re.DOTALL,
        )
        assert re.search(
            r"if\s*\(\s*!\s*m_calendarEnabled\s*\|\|\s*"
            r"m_schedule\.entries\.empty\(\)\s*\)\s*\{\s*return\s+true\s*;",
            egress_body,
            re.DOTALL,
        )
        assert load_body.rfind("m_calendarEnabled = true") > load_body.rfind(
            "totalSlots != m_frameSlots"
        )
