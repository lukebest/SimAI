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
