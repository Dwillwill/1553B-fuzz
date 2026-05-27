from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import random
from typing import Dict, Iterator, List, Sequence

from .cases import DATA_WORDS, FuzzCase


BCMSG_FMT_RT2RT = 0x00000001


@dataclass
class StrategyConfig:
    rt_targets: Sequence[int]
    subaddresses: Sequence[int]
    word_counts: Sequence[int]
    mode_codes: Sequence[int]
    delay_100ns: int
    seed: int

    @classmethod
    def defaults(cls, seed: int = 1) -> "StrategyConfig":
        return cls(
            rt_targets=[0, 1, 2, 30, 31],
            subaddresses=[0, 1, 2, 30, 31],
            word_counts=[0, 1, 2, 16, 31],
            mode_codes=[0, 1, 2, 4, 5, 8, 16, 17, 31],
            delay_100ns=1000,
            seed=seed,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, object], seed: int = 1) -> "StrategyConfig":
        base = cls.defaults(seed=seed)
        return cls(
            rt_targets=_int_list(data.get("rt_targets"), base.rt_targets),
            subaddresses=_int_list(data.get("subaddresses"), base.subaddresses),
            word_counts=_int_list(data.get("word_counts"), base.word_counts),
            mode_codes=_int_list(data.get("mode_codes"), base.mode_codes),
            delay_100ns=int(data.get("delay_100ns", base.delay_100ns)),
            seed=int(data.get("seed", seed)),
        )


def generate_cases(
    strategy_names: Sequence[str],
    config: StrategyConfig,
    limit: int,
) -> Iterator[FuzzCase]:
    generators = {
        "cmd_boundary": cmd_boundary_cases,
        "mode_code": mode_code_cases,
        "broadcast": broadcast_cases,
        "rt_to_rt": rt_to_rt_cases,
        "data_pattern": data_pattern_cases,
        "random": random_cases,
    }

    emitted = 0
    for name in strategy_names:
        if name not in generators:
            raise ValueError("unknown strategy: %s" % name)
        for case in generators[name](config):
            yield case
            emitted += 1
            if limit > 0 and emitted >= limit:
                return


def cmd_boundary_cases(config: StrategyConfig) -> Iterator[FuzzCase]:
    idx = 0
    patterns = data_patterns()
    for rt in config.rt_targets:
        for tx_rx in [0, 1]:
            for subaddr in config.subaddresses:
                for count in config.word_counts:
                    yield FuzzCase(
                        case_id=_case_id("cmd_boundary", idx),
                        strategy="cmd_boundary",
                        rt_addr=rt,
                        tx_rx=tx_rx,
                        subaddr=subaddr,
                        word_count=count,
                        data_words=patterns[idx % len(patterns)],
                        delay_100ns=config.delay_100ns,
                        notes="boundary command-word field combination",
                    ).normalized()
                    idx += 1


def mode_code_cases(config: StrategyConfig) -> Iterator[FuzzCase]:
    idx = 0
    patterns = data_patterns()
    for rt in config.rt_targets:
        for subaddr in [0, 31]:
            for tx_rx in [0, 1]:
                for mode in config.mode_codes:
                    yield FuzzCase(
                        case_id=_case_id("mode_code", idx),
                        strategy="mode_code",
                        rt_addr=rt,
                        tx_rx=tx_rx,
                        subaddr=subaddr,
                        word_count=mode,
                        data_words=patterns[idx % len(patterns)],
                        delay_100ns=config.delay_100ns,
                        notes="mode-code command through subaddress 0 or 31",
                    ).normalized()
                    idx += 1


def broadcast_cases(config: StrategyConfig) -> Iterator[FuzzCase]:
    idx = 0
    patterns = data_patterns()
    for subaddr in config.subaddresses:
        for count in config.word_counts:
            yield FuzzCase(
                case_id=_case_id("broadcast", idx),
                strategy="broadcast",
                rt_addr=31,
                tx_rx=0,
                subaddr=subaddr,
                word_count=count,
                data_words=patterns[idx % len(patterns)],
                delay_100ns=config.delay_100ns,
                notes="broadcast command to RT address 31",
            ).normalized()
            idx += 1


def rt_to_rt_cases(config: StrategyConfig) -> Iterator[FuzzCase]:
    idx = 0
    patterns = data_patterns()
    rx_targets = [rt for rt in config.rt_targets if rt != 31]
    tx_targets = [rt for rt in config.rt_targets if rt != 31]
    for rx_rt in rx_targets:
        for tx_rt in tx_targets:
            if rx_rt == tx_rt:
                continue
            for subaddr in [1, 30]:
                for count in [0, 1, 31]:
                    yield FuzzCase(
                        case_id=_case_id("rt_to_rt", idx),
                        strategy="rt_to_rt",
                        rt_addr=rx_rt,
                        tx_rx=0,
                        subaddr=subaddr,
                        word_count=count,
                        is_rt_to_rt=1,
                        rt2_addr=tx_rt,
                        rt2_tx_rx=1,
                        rt2_subaddr=subaddr,
                        rt2_word_count=count,
                        bcmsg_fmt=BCMSG_FMT_RT2RT,
                        data_words=patterns[idx % len(patterns)],
                        delay_100ns=config.delay_100ns,
                        notes="RT-to-RT transfer: CMD1 receive, CMD2 transmit",
                    ).normalized()
                    idx += 1


def data_pattern_cases(config: StrategyConfig) -> Iterator[FuzzCase]:
    for idx, pattern in enumerate(data_patterns()):
        yield FuzzCase(
            case_id=_case_id("data_pattern", idx),
            strategy="data_pattern",
            rt_addr=_first_non_broadcast(config.rt_targets),
            tx_rx=0,
            subaddr=1,
            word_count=0,
            data_words=pattern,
            delay_100ns=config.delay_100ns,
            notes="32-word payload data-pattern case",
        ).normalized()


def random_cases(config: StrategyConfig) -> Iterator[FuzzCase]:
    rng = random.Random(config.seed)
    idx = 0
    while True:
        count = rng.choice(list(config.word_counts))
        yield FuzzCase(
            case_id=_case_id("random", idx),
            strategy="random",
            rt_addr=rng.choice(list(config.rt_targets)),
            tx_rx=rng.choice([0, 1]),
            subaddr=rng.choice(list(config.subaddresses)),
            word_count=count,
            data_words=[rng.randrange(0, 0x10000) for _ in range(DATA_WORDS)],
            delay_100ns=config.delay_100ns,
            notes="seeded pseudo-random field and payload mutation",
        ).normalized()
        idx += 1


def data_patterns() -> List[List[int]]:
    return [
        [0x0000] * DATA_WORDS,
        [0xFFFF] * DATA_WORDS,
        [0xAAAA] * DATA_WORDS,
        [0x5555] * DATA_WORDS,
        [0x8000] * DATA_WORDS,
        [0x7FFF] * DATA_WORDS,
        list(range(DATA_WORDS)),
        list(reversed(range(DATA_WORDS))),
        [(0x1000 + i) & 0xFFFF for i in range(DATA_WORDS)],
        [0x0000, 0xFFFF, 0x8000, 0x7FFF] * 8,
    ]


def _case_id(strategy: str, idx: int) -> str:
    return "%s-%06d" % (strategy, idx)


def _first_non_broadcast(values: Sequence[int]) -> int:
    for value in values:
        if int(value) != 31:
            return int(value)
    return 1


def _int_list(value: object, default: Sequence[int]) -> Sequence[int]:
    if value is None:
        return list(default)
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        raise TypeError("expected a list of integers")
    return [int(item) for item in value]
