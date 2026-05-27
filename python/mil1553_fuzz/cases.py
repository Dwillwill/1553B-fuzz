from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


DATA_WORDS = 32
NO_NEXT = 0xFFFFFFFF


def _u8(value: int) -> int:
    return int(value) & 0xFF


def _u16(value: int) -> int:
    return int(value) & 0xFFFF


def _u32(value: int) -> int:
    return int(value) & 0xFFFFFFFF


def make_command_word(rt_addr: int, tx_rx: int, subaddr: int, word_count: int) -> int:
    """Build a 1553 command word for logs and mock readback.

    The vendor API builds command words in native code. Python keeps this helper
    for dry-run output and replay logs.
    """
    return (
        ((_u8(rt_addr) & 0x1F) << 11)
        | ((_u8(tx_rx) & 0x01) << 10)
        | ((_u8(subaddr) & 0x1F) << 5)
        | (_u8(word_count) & 0x1F)
    )


@dataclass
class FuzzCase:
    case_id: str
    strategy: str
    rt_addr: int
    tx_rx: int
    subaddr: int
    word_count: int
    data_words: List[int] = field(default_factory=lambda: [0] * DATA_WORDS)
    is_rt_to_rt: int = 0
    rt2_addr: int = 0
    rt2_tx_rx: int = 0
    rt2_subaddr: int = 0
    rt2_word_count: int = 0
    bcmsg_fmt: int = 0
    bcmsg_rty: int = 0
    delay_100ns: int = 1000
    sched_time_100ns: int = 0
    frame_time_100ns: int = 0
    next_msg_num: int = 0
    notes: str = ""

    def normalized(self) -> "FuzzCase":
        words = list(self.data_words[:DATA_WORDS])
        if len(words) < DATA_WORDS:
            words.extend([0] * (DATA_WORDS - len(words)))

        return FuzzCase(
            case_id=self.case_id,
            strategy=self.strategy,
            rt_addr=_u8(self.rt_addr),
            tx_rx=_u8(self.tx_rx),
            subaddr=_u8(self.subaddr),
            word_count=_u8(self.word_count),
            data_words=[_u32(word) for word in words],
            is_rt_to_rt=1 if self.is_rt_to_rt else 0,
            rt2_addr=_u8(self.rt2_addr),
            rt2_tx_rx=_u8(self.rt2_tx_rx),
            rt2_subaddr=_u8(self.rt2_subaddr),
            rt2_word_count=_u8(self.rt2_word_count),
            bcmsg_fmt=_u32(self.bcmsg_fmt),
            bcmsg_rty=_u32(self.bcmsg_rty),
            delay_100ns=_u32(self.delay_100ns),
            sched_time_100ns=_u32(self.sched_time_100ns),
            frame_time_100ns=_u32(self.frame_time_100ns),
            next_msg_num=_u32(self.next_msg_num),
            notes=self.notes,
        )

    @property
    def cmd1(self) -> int:
        return make_command_word(self.rt_addr, self.tx_rx, self.subaddr, self.word_count)

    @property
    def cmd2(self) -> Optional[int]:
        if not self.is_rt_to_rt:
            return None
        return make_command_word(
            self.rt2_addr,
            self.rt2_tx_rx,
            self.rt2_subaddr,
            self.rt2_word_count,
        )

    def to_dict(self) -> Dict[str, Any]:
        case = self.normalized()
        return {
            "case_id": case.case_id,
            "strategy": case.strategy,
            "rt_addr": case.rt_addr,
            "tx_rx": case.tx_rx,
            "subaddr": case.subaddr,
            "word_count": case.word_count,
            "is_rt_to_rt": case.is_rt_to_rt,
            "rt2_addr": case.rt2_addr,
            "rt2_tx_rx": case.rt2_tx_rx,
            "rt2_subaddr": case.rt2_subaddr,
            "rt2_word_count": case.rt2_word_count,
            "bcmsg_fmt": case.bcmsg_fmt,
            "bcmsg_rty": case.bcmsg_rty,
            "delay_100ns": case.delay_100ns,
            "sched_time_100ns": case.sched_time_100ns,
            "frame_time_100ns": case.frame_time_100ns,
            "next_msg_num": case.next_msg_num,
            "cmd1": "0x%04x" % case.cmd1,
            "cmd2": None if case.cmd2 is None else "0x%04x" % case.cmd2,
            "data_words": ["0x%04x" % _u16(word) for word in case.data_words],
            "notes": case.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FuzzCase":
        raw_words = data.get("data_words", [])
        words = [_parse_int(word) for word in raw_words]
        return cls(
            case_id=str(data["case_id"]),
            strategy=str(data.get("strategy", "replay")),
            rt_addr=_parse_int(data.get("rt_addr", 0)),
            tx_rx=_parse_int(data.get("tx_rx", 0)),
            subaddr=_parse_int(data.get("subaddr", 0)),
            word_count=_parse_int(data.get("word_count", 0)),
            data_words=words,
            is_rt_to_rt=_parse_int(data.get("is_rt_to_rt", 0)),
            rt2_addr=_parse_int(data.get("rt2_addr", 0)),
            rt2_tx_rx=_parse_int(data.get("rt2_tx_rx", 0)),
            rt2_subaddr=_parse_int(data.get("rt2_subaddr", 0)),
            rt2_word_count=_parse_int(data.get("rt2_word_count", 0)),
            bcmsg_fmt=_parse_int(data.get("bcmsg_fmt", 0)),
            bcmsg_rty=_parse_int(data.get("bcmsg_rty", 0)),
            delay_100ns=_parse_int(data.get("delay_100ns", 1000)),
            sched_time_100ns=_parse_int(data.get("sched_time_100ns", 0)),
            frame_time_100ns=_parse_int(data.get("frame_time_100ns", 0)),
            next_msg_num=_parse_int(data.get("next_msg_num", 0)),
            notes=str(data.get("notes", "")),
        ).normalized()


@dataclass
class Readback:
    cdp_sts: int = 0
    time_tag_h: int = 0
    time_tag_l: int = 0
    cmd1: int = 0
    cmd2: int = 0
    rt_sts1: int = 0
    rt_sts2: int = 0
    msg_data: List[int] = field(default_factory=lambda: [0] * DATA_WORDS)

    def to_dict(self) -> Dict[str, Any]:
        words = list(self.msg_data[:DATA_WORDS])
        if len(words) < DATA_WORDS:
            words.extend([0] * (DATA_WORDS - len(words)))
        return {
            "cdp_sts": "0x%08x" % _u32(self.cdp_sts),
            "time_tag_h": "0x%08x" % _u32(self.time_tag_h),
            "time_tag_l": "0x%08x" % _u32(self.time_tag_l),
            "cmd1": "0x%04x" % _u16(self.cmd1),
            "cmd2": "0x%04x" % _u16(self.cmd2),
            "rt_sts1": "0x%08x" % _u32(self.rt_sts1),
            "rt_sts2": "0x%08x" % _u32(self.rt_sts2),
            "msg_data": ["0x%04x" % _u16(word) for word in words],
        }


def event_record(case: FuzzCase, status: str, readback: Optional[Readback] = None) -> Dict[str, Any]:
    record = {
        "status": status,
        "case": case.to_dict(),
    }
    if readback is not None:
        record["readback"] = readback.to_dict()
    return record


def load_cases(items: Iterable[Dict[str, Any]]) -> List[FuzzCase]:
    return [FuzzCase.from_dict(item) for item in items]


def _parse_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    return int(value)
