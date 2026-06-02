from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Callable, Dict, Iterable, Iterator, Optional, Sequence

from .adapters import BoardAdapter
from .cases import FuzzCase, event_record


SEND_FROM_CHB = 0x00000800

ProgressCallback = Callable[[int, FuzzCase, Dict[str, object]], None]


def apply_bus(cases: Iterable[FuzzCase], bus: str) -> Iterator[FuzzCase]:
    use_bus_b = bus.upper() == "B"
    for case in cases:
        normalized = case.normalized()
        if use_bus_b:
            normalized.bcmsg_fmt |= SEND_FROM_CHB
        else:
            normalized.bcmsg_fmt &= ~SEND_FROM_CHB
        yield normalized


def repeat_cases(cases: Sequence[FuzzCase], repeat_each: int) -> Iterator[FuzzCase]:
    repeat_each = max(1, int(repeat_each))
    for case in cases:
        for repeat_index in range(repeat_each):
            repeated = case.normalized()
            if repeat_each > 1:
                repeated.case_id = "%s-r%02d" % (case.case_id, repeat_index + 1)
            yield repeated


def run_campaign(
    adapter: BoardAdapter,
    cases: Sequence[FuzzCase],
    timeout_ms: int,
    interval_ms: int,
    out_path: str,
    progress: Optional[ProgressCallback] = None,
) -> int:
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    adapter.open()
    try:
        with output.open("w", encoding="utf-8") as fp:
            for index, case in enumerate(cases, start=1):
                readback = adapter.run_case(case, timeout_ms)
                record = event_record(case, "executed", readback)
                fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                fp.write("\n")
                fp.flush()
                count += 1
                if progress is not None:
                    progress(index, case, record)
                if interval_ms > 0 and index < len(cases):
                    time.sleep(interval_ms / 1000.0)
    finally:
        adapter.close()

    return count


def write_dry_run(cases: Sequence[FuzzCase], out_path: str) -> int:
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fp:
        for case in cases:
            fp.write(json.dumps(event_record(case, "generated"), ensure_ascii=False, sort_keys=True))
            fp.write("\n")
    return len(cases)
