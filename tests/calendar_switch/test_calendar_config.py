"""
Contract tests for calendar switch configuration parsing.
"""
import re
from pathlib import Path


COMMON_H = Path("astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h")
TEMPLATE_CONF = Path("astra-sim-alibabacloud/inputs/config/SimAI.calendar.conf")

REQUIRED_KEYS = [
    "ENABLE_CALENDAR_SWITCH",
    "CALENDAR_SLOT_NS",
    "CALENDAR_FRAME_SLOTS",
    "CALENDAR_GRANULARITY_MODE",
    "CALENDAR_ALGORITHM",
    "CALENDAR_TRACE_ENABLE",
    "CALENDAR_TRACE_FILE",
]

REQUIRED_DEFAULTS = [
    r"uint32_t\s+enable_calendar_switch\s*=\s*0\s*;",
    r"uint32_t\s+calendar_slot_ns\s*=\s*1000\s*;",
    r"uint32_t\s+calendar_frame_slots\s*=\s*1024\s*;",
    r'std::string\s+calendar_granularity_mode\s*=\s*"operator"\s*;',
    r'std::string\s+calendar_algorithm\s*=\s*"solstice"\s*;',
    r"uint32_t\s+calendar_trace_enable\s*=\s*0\s*;",
    r'std::string\s+calendar_trace_file\s*=\s*""\s*;',
]


class TestCalendarConfig:
    def test_common_h_parses_all_required_keys(self):
        code = COMMON_H.read_text()

        for key in REQUIRED_KEYS:
            pattern = rf'key\.compare\("{key}"\)'
            assert re.search(pattern, code), f"common.h missing parse for {key}"

    def test_common_h_declares_all_default_variables(self):
        code = COMMON_H.read_text()

        for pattern in REQUIRED_DEFAULTS:
            assert re.search(pattern, code), f"common.h missing default matching {pattern}"

    def test_template_conf_has_all_required_keys(self):
        text = TEMPLATE_CONF.read_text()
        keys_in_file = set()

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            keys_in_file.add(line.split()[0])

        for key in REQUIRED_KEYS:
            assert key in keys_in_file, f"Template config missing {key}"

    def test_default_disables_calendar(self):
        code = COMMON_H.read_text()

        assert re.search(r"enable_calendar_switch\s*=\s*0", code)

    def test_common_h_includes_calendar_switch_header(self):
        code = COMMON_H.read_text()

        assert "#include <ns3/calendar-switch-node.h>" in code

    def test_common_h_creates_calendar_switch_node_when_enabled(self):
        code = COMMON_H.read_text()

        pattern = (
            r"else\s*if\s*\(\s*node_type\[i\]\s*==\s*1\s*\)\s*\{"
            r".*?if\s*\(\s*enable_calendar_switch\s*\)\s*\{"
            r".*?CreateObject\s*<\s*CalendarSwitchNode\s*>\s*\(\s*\)"
        )
        assert re.search(pattern, code, re.DOTALL), (
            "common.h should create CalendarSwitchNode for switch nodes "
            "when enable_calendar_switch is set"
        )

    def test_common_h_keeps_plain_switchnode_baseline_branch(self):
        code = COMMON_H.read_text()

        pattern = (
            r"else\s*if\s*\(\s*node_type\[i\]\s*==\s*1\s*\)\s*\{"
            r".*?else\s*\{"
            r".*?CreateObject\s*<\s*SwitchNode\s*>\s*\(\s*\)"
        )
        assert re.search(pattern, code, re.DOTALL), (
            "common.h should keep creating plain SwitchNode when calendar "
            "switching is disabled"
        )

    def test_common_h_sets_ecn_enabled_in_both_branches(self):
        code = COMMON_H.read_text()

        calendar_pattern = (
            r"if\s*\(\s*enable_calendar_switch\s*\)\s*\{"
            r"(?:(?!\}\s*else).)*?"
            r"SetAttribute\s*\(\s*\"EcnEnabled\"\s*,\s*BooleanValue\s*\(\s*enable_qcn\s*\)\s*\)"
        )
        baseline_pattern = (
            r"else\s*\{"
            r"(?:(?!\}\s*else\s+if\s*\(\s*node_type\[i\]\s*==\s*2\s*\)).)*?"
            r"SetAttribute\s*\(\s*\"EcnEnabled\"\s*,\s*BooleanValue\s*\(\s*enable_qcn\s*\)\s*\)"
        )
        assert re.search(calendar_pattern, code, re.DOTALL), (
            "CalendarSwitchNode branch should preserve EcnEnabled setup"
        )
        assert re.search(baseline_pattern, code, re.DOTALL), (
            "SwitchNode baseline branch should preserve EcnEnabled setup"
        )
