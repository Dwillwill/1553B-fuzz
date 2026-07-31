from __future__ import annotations

import time
import unittest

from mil1553_fuzz.web_gui import WebCampaignController, _parse_campaign_config


def _payload(**overrides):
    payload = {
        "scenarios": ["bc_rt_control", "rt_bc_data_report"],
        "strategies": ["bit_level", "semantic"],
        "backend": "mock",
        "dll_path": "board_adapter/mil1553_board_adapter.dll",
        "card_index": "0",
        "channel": "0",
        "bus": "A",
        "rt_targets": "1",
        "subaddresses": "1",
        "word_counts": "1,2,16,0",
        "rt2_source": "2",
        "rt3_destination": "3",
        "limit": "8",
        "repeat_each": "1",
        "interval_ms": "0",
        "timeout_ms": "3000",
        "seed": "1",
        "out_path": "runs/test_web_gui.jsonl",
        "no_reset": False,
        "dry_run": False,
    }
    payload.update(overrides)
    return payload


class WebGuiConfigTests(unittest.TestCase):
    def test_parses_browser_payload_and_generates_requested_cases(self) -> None:
        config = _parse_campaign_config(_payload(limit="12", repeat_each="2"))

        self.assertEqual(config["backend"], "mock")
        self.assertEqual(config["bus"], "A")
        self.assertEqual(len(config["cases"]), 24)

    def test_rejects_missing_scenario_selection(self) -> None:
        with self.assertRaisesRegex(ValueError, "测试场景"):
            _parse_campaign_config(_payload(scenarios=[]))


class WebCampaignControllerTests(unittest.TestCase):
    def test_mock_campaign_reports_progress_and_completion(self) -> None:
        controller = WebCampaignController()
        controller.start(_payload(limit="5"))

        deadline = time.monotonic() + 5
        while controller.snapshot()["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
        snapshot = controller.snapshot()

        self.assertFalse(snapshot["running"])
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["current"], 5)
        self.assertEqual(snapshot["total"], 5)
        self.assertTrue(any(item["level"] == "success" for item in snapshot["logs"]))

    def test_stop_interrupts_campaign_interval(self) -> None:
        controller = WebCampaignController()
        controller.start(_payload(limit="20", interval_ms="5000"))

        deadline = time.monotonic() + 2
        while controller.snapshot()["current"] == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        controller.request_stop()

        deadline = time.monotonic() + 3
        while controller.snapshot()["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
        snapshot = controller.snapshot()

        self.assertFalse(snapshot["running"])
        self.assertEqual(snapshot["status"], "stopped")
        self.assertLess(snapshot["current"], snapshot["total"])


if __name__ == "__main__":
    unittest.main()
