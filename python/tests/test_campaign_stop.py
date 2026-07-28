from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from mil1553_fuzz.adapters import BoardAdapter
from mil1553_fuzz.campaign import run_campaign
from mil1553_fuzz.cases import FuzzCase, Readback


class TrackingAdapter(BoardAdapter):
    def __init__(self) -> None:
        self.opened = False
        self.closed = False
        self.stop_count = 0

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False
        self.closed = True

    def stop(self) -> None:
        self.stop_count += 1

    def run_case(self, case: FuzzCase, timeout_ms: int) -> Readback:
        return Readback(cmd1=case.cmd1)


class CampaignStopTests(unittest.TestCase):
    def test_stop_interrupts_long_interval_and_closes_adapter(self) -> None:
        adapter = TrackingAdapter()
        stop_event = threading.Event()
        cases = [FuzzCase(str(index), "test", 1, 0, 1, 1) for index in range(10)]

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run.jsonl"
            threading.Timer(0.1, stop_event.set).start()
            started = time.monotonic()
            count = run_campaign(
                adapter=adapter,
                cases=cases,
                timeout_ms=3000,
                interval_ms=5000,
                out_path=str(output),
                stop_event=stop_event,
            )
            elapsed = time.monotonic() - started

        self.assertEqual(count, 1)
        self.assertLess(elapsed, 1.0)
        self.assertTrue(adapter.closed)
        self.assertGreaterEqual(adapter.stop_count, 1)

    def test_pre_cancelled_campaign_does_not_open_adapter(self) -> None:
        adapter = TrackingAdapter()
        stop_event = threading.Event()
        stop_event.set()

        with tempfile.TemporaryDirectory() as temp_dir:
            count = run_campaign(
                adapter=adapter,
                cases=[FuzzCase("one", "test", 1, 0, 1, 1)],
                timeout_ms=3000,
                interval_ms=0,
                out_path=str(Path(temp_dir) / "run.jsonl"),
                stop_event=stop_event,
            )

        self.assertEqual(count, 0)
        self.assertFalse(adapter.opened)
        self.assertFalse(adapter.closed)


if __name__ == "__main__":
    unittest.main()
