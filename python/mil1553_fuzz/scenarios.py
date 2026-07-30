from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Dict, Iterator, List, Sequence

from .cases import DATA_WORDS, FuzzCase


BCMSG_FMT_RT2RT = 0x00000001
MODE_SYNCHRONIZE = 0x01
MODE_TRANSMIT_STATUS = 0x02
MODE_SYNCHRONIZE_WITH_DATA = 0x11
MODE_TRANSMIT_LAST_COMMAND = 0x12
MODE_SUBADDRESS = 0x1F

SCENARIO_NAMES = [
    "bc_rt_control",
    "bc_rt_sync_data",
    "bc_broadcast_data",
    "bc_broadcast_sync_data",
    "bc_broadcast_sync_no_data",
    "rt2_rt3_transfer",
    "last_command_readback",
    "bc_query_rt_status",
    "rt_bc_data_report",
]


@dataclass
class ScenarioConfig:
    rt_targets: Sequence[int]
    subaddresses: Sequence[int]
    word_counts: Sequence[int]
    rt2_source: int
    rt3_destination: int
    delay_100ns: int
    seed: int

    @classmethod
    def defaults(cls, seed: int = 1) -> "ScenarioConfig":
        return cls(
            rt_targets=[1],
            subaddresses=[1],
            word_counts=[1, 2, 16, 0],
            rt2_source=2,
            rt3_destination=3,
            delay_100ns=1000,
            seed=seed,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, object], seed: int = 1) -> "ScenarioConfig":
        base = cls.defaults(seed)
        return cls(
            rt_targets=_int_list(data.get("rt_targets"), base.rt_targets),
            subaddresses=_int_list(data.get("subaddresses"), base.subaddresses),
            word_counts=_int_list(data.get("word_counts"), base.word_counts),
            rt2_source=int(data.get("rt2_source", base.rt2_source)),
            rt3_destination=int(data.get("rt3_destination", base.rt3_destination)),
            delay_100ns=int(data.get("delay_100ns", base.delay_100ns)),
            seed=int(data.get("seed", seed)),
        )

    def validate(self) -> None:
        if not self.rt_targets:
            raise ValueError("rt_targets must not be empty")
        if not self.subaddresses:
            raise ValueError("subaddresses must not be empty")
        if not self.word_counts:
            raise ValueError("word_counts must not be empty")
        if self.rt2_source == self.rt3_destination:
            raise ValueError("RT2 source and RT3 destination must be different")
        for value in list(self.rt_targets) + [self.rt2_source, self.rt3_destination]:
            if not 0 <= int(value) <= 30:
                raise ValueError("unicast RT addresses must be between 0 and 30")
        for value in self.subaddresses:
            if not 1 <= int(value) <= 30:
                raise ValueError("ordinary data subaddresses must be between 1 and 30")
        for value in self.word_counts:
            if not 0 <= int(value) <= 31:
                raise ValueError("word counts must be between 0 and 31")


def generate_scenario_cases(name: str, config: ScenarioConfig) -> Iterator[FuzzCase]:
    config.validate()
    generators = {
        "bc_rt_control": _bc_rt_control,
        "bc_rt_sync_data": _bc_rt_sync_data,
        "bc_broadcast_data": _bc_broadcast_data,
        "bc_broadcast_sync_data": _bc_broadcast_sync_data,
        "bc_broadcast_sync_no_data": _bc_broadcast_sync_no_data,
        "rt2_rt3_transfer": _rt2_rt3_transfer,
        "last_command_readback": _last_command_readback,
        "bc_query_rt_status": _bc_query_rt_status,
        "rt_bc_data_report": _rt_bc_data_report,
    }
    if name not in generators:
        raise ValueError("unknown scenario: %s" % name)
    yield from generators[name](config)


def _bc_rt_control(config: ScenarioConfig) -> Iterator[FuzzCase]:
    index = 0
    for rt in config.rt_targets:
        for subaddr in config.subaddresses:
            for count in config.word_counts:
                yield _case(
                    "bc_rt_control",
                    index,
                    rt,
                    0,
                    subaddr,
                    count,
                    config,
                    "BC sends a control/data message to one RT",
                )
                index += 1


def _bc_rt_sync_data(config: ScenarioConfig) -> Iterator[FuzzCase]:
    for index, rt in enumerate(config.rt_targets):
        yield _case(
            "bc_rt_sync_data",
            index,
            rt,
            0,
            MODE_SUBADDRESS,
            MODE_SYNCHRONIZE_WITH_DATA,
            config,
            "unicast Synchronize With Data mode command",
            data_words=_payload(index, 1),
        )


def _bc_broadcast_data(config: ScenarioConfig) -> Iterator[FuzzCase]:
    index = 0
    for subaddr in config.subaddresses:
        for count in config.word_counts:
            yield _case(
                "bc_broadcast_data",
                index,
                31,
                0,
                subaddr,
                count,
                config,
                "BC broadcasts ordinary data to all RTs",
            )
            index += 1


def _bc_broadcast_sync_data(config: ScenarioConfig) -> Iterator[FuzzCase]:
    yield _case(
        "bc_broadcast_sync_data",
        0,
        31,
        0,
        MODE_SUBADDRESS,
        MODE_SYNCHRONIZE_WITH_DATA,
        config,
        "broadcast Synchronize With Data mode command",
        data_words=_payload(0, 1),
    )


def _bc_broadcast_sync_no_data(config: ScenarioConfig) -> Iterator[FuzzCase]:
    yield _case(
        "bc_broadcast_sync_no_data",
        0,
        31,
        1,
        MODE_SUBADDRESS,
        MODE_SYNCHRONIZE,
        config,
        "broadcast Synchronize mode command without data (vendor example convention)",
        data_words=[0] * DATA_WORDS,
    )


def _rt2_rt3_transfer(config: ScenarioConfig) -> Iterator[FuzzCase]:
    index = 0
    for subaddr in config.subaddresses:
        for count in config.word_counts:
            # The vendor API follows the 1553 bus order: receiver command first,
            # then transmitter command. The data direction remains RT2 -> RT3.
            yield FuzzCase(
                case_id=_case_id("rt2_rt3_transfer", index),
                scenario="rt2_rt3_transfer",
                strategy="baseline",
                rt_addr=config.rt3_destination,
                tx_rx=0,
                subaddr=subaddr,
                word_count=count,
                is_rt_to_rt=1,
                rt2_addr=config.rt2_source,
                rt2_tx_rx=1,
                rt2_subaddr=subaddr,
                rt2_word_count=count,
                bcmsg_fmt=BCMSG_FMT_RT2RT,
                data_words=_payload(index, _word_count(count)),
                delay_100ns=config.delay_100ns,
                notes="RT2 transmits to RT3; CMD1=RT3 receive, CMD2=RT2 transmit",
            ).normalized()
            index += 1


def _last_command_readback(config: ScenarioConfig) -> Iterator[FuzzCase]:
    for index, rt in enumerate(config.rt_targets):
        yield _case(
            "last_command_readback",
            index,
            rt,
            1,
            MODE_SUBADDRESS,
            MODE_TRANSMIT_LAST_COMMAND,
            config,
            "BC requests the RT last-command word",
            data_words=[0] * DATA_WORDS,
        )


def _bc_query_rt_status(config: ScenarioConfig) -> Iterator[FuzzCase]:
    for index, rt in enumerate(config.rt_targets):
        yield _case(
            "bc_query_rt_status",
            index,
            rt,
            1,
            MODE_SUBADDRESS,
            MODE_TRANSMIT_STATUS,
            config,
            "BC requests the RT status word",
            data_words=[0] * DATA_WORDS,
        )


def _rt_bc_data_report(config: ScenarioConfig) -> Iterator[FuzzCase]:
    index = 0
    for rt in config.rt_targets:
        for subaddr in config.subaddresses:
            for count in config.word_counts:
                yield _case(
                    "rt_bc_data_report",
                    index,
                    rt,
                    1,
                    subaddr,
                    count,
                    config,
                    "BC requests an RT data report",
                    data_words=[0] * DATA_WORDS,
                )
                index += 1


def _case(
    scenario: str,
    index: int,
    rt_addr: int,
    tx_rx: int,
    subaddr: int,
    word_count: int,
    config: ScenarioConfig,
    notes: str,
    data_words: List[int] | None = None,
) -> FuzzCase:
    return FuzzCase(
        case_id=_case_id(scenario, index),
        scenario=scenario,
        strategy="baseline",
        rt_addr=rt_addr,
        tx_rx=tx_rx,
        subaddr=subaddr,
        word_count=word_count,
        data_words=data_words if data_words is not None else _payload(index, _word_count(word_count)),
        delay_100ns=config.delay_100ns,
        notes=notes,
    ).normalized()


def _payload(seed: int, count: int) -> List[int]:
    words = [0] * DATA_WORDS
    for index in range(min(count, DATA_WORDS)):
        words[index] = (0x1000 + ((seed & 0xFF) << 5) + index) & 0xFFFF
    return words


def _word_count(encoded_count: int) -> int:
    return 32 if int(encoded_count) == 0 else int(encoded_count) & 0x1F


def _case_id(scenario: str, index: int) -> str:
    return "%s-base-%04d" % (scenario, index)


def _int_list(value: object, default: Sequence[int]) -> Sequence[int]:
    if value is None:
        return list(default)
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        raise TypeError("expected a list of integers")
    return [int(item) for item in value]
