from __future__ import annotations

import itertools
from typing import Optional

from .adapters import BoardAdapter
from .cases import FuzzCase, Readback


class MockAdapter(BoardAdapter):
    """Offline adapter for laptops without a 1553B board.

    It does not simulate electrical behavior. It only returns deterministic
    readback-like records so the fuzz runner, logging, and replay pipeline can
    be developed without hardware.
    """

    def __init__(self, channel: int = 0) -> None:
        self.channel = channel
        self._opened = False
        self._seq = itertools.count(1)

    def open(self) -> None:
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def run_case(self, case: FuzzCase, timeout_ms: int) -> Readback:
        if not self._opened:
            raise RuntimeError("mock adapter is not open")

        normalized = case.normalized()
        seq = next(self._seq)
        return Readback(
            cdp_sts=self._mock_status(normalized),
            time_tag_h=0,
            time_tag_l=seq,
            cmd1=normalized.cmd1,
            cmd2=normalized.cmd2 or 0,
            rt_sts1=self._mock_rt_status(normalized),
            rt_sts2=0,
            msg_data=list(normalized.data_words),
        )

    def _mock_status(self, case: FuzzCase) -> int:
        status = 0
        if case.is_rt_to_rt:
            status |= 0x0040
        if _looks_suspicious(case):
            status |= 0x1000
        return status

    def _mock_rt_status(self, case: FuzzCase) -> int:
        if case.rt_addr == 31:
            return 0
        if _looks_suspicious(case):
            return 0x00000001
        return 0


def _looks_suspicious(case: FuzzCase) -> bool:
    if case.subaddr in (0, 31) and case.word_count not in (0, 1, 2, 4, 5, 8, 16, 17):
        return True
    if case.rt_addr == 31 and case.tx_rx == 1:
        return True
    return False
