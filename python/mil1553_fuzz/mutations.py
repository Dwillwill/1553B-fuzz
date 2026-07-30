from __future__ import annotations

from dataclasses import replace
import random
from typing import List, Tuple

from .cases import FuzzCase, make_command_word


MUTATION_STRATEGY_NAMES = ["bit_level", "structured", "semantic"]


def bit_reverse_range(
    value: int,
    start: int = 0,
    length: int = 16,
    rng: random.Random | None = None,
) -> int:
    if start < 0 or length <= 0 or start + length > 16:
        raise ValueError("bit range must stay within the 16-bit command word")
    random_source = rng or random
    mode = random_source.choice(["reverse", "flip", "hybrid"])
    result = int(value) & 0xFFFF

    if mode in {"reverse", "hybrid"}:
        for index in range(length // 2):
            low = start + index
            high = start + length - 1 - index
            if ((result >> low) & 1) != ((result >> high) & 1):
                result ^= (1 << low) | (1 << high)

    if mode in {"flip", "hybrid"}:
        bit = start + random_source.randint(0, length - 1)
        result ^= 1 << bit

    return result & 0xFFFF


def structured_fuzz(rng: random.Random | None = None) -> int:
    random_source = rng or random
    rt = random_source.choice([0, 1, 4, 6, 15, 31])
    tx_rx = random_source.choice([0, 1])
    if random_source.random() < 0.3:
        subaddr = random_source.choice([0, 31])
        word_count = random_source.choice([0x04, 0x10, 0x11, 0x12])
    else:
        subaddr = random_source.randint(1, 30)
        word_count = random_source.randint(1, 32) & 0x1F
    return make_command_word(rt, tx_rx, subaddr, word_count)


def semantic_fuzz_command(
    base_value: int,
    rng: random.Random | None = None,
) -> Tuple[int, str]:
    random_source = rng or random
    rt = (base_value >> 11) & 0x1F
    tx_rx = (base_value >> 10) & 0x01
    subaddr = (base_value >> 5) & 0x1F
    word_count = base_value & 0x1F
    mode = random_source.choice(
        [
            "word_count_mismatch",
            "invalid_rt",
            "invalid_subaddr",
            "tr_conflict",
            "broadcast_misuse",
        ]
    )

    if mode == "word_count_mismatch":
        word_count = random_source.choice([0, 31, word_count + 5, word_count - 3])
    elif mode == "invalid_rt":
        rt = random_source.choice([0, 31, 32, 255]) & 0x1F
    elif mode == "invalid_subaddr":
        subaddr = random_source.choice([0, 31])
    elif mode == "tr_conflict":
        tx_rx = 1 - tx_rx
    elif mode == "broadcast_misuse":
        rt = 31
        tx_rx = 1

    fuzzed = make_command_word(rt, tx_rx, subaddr, word_count)
    return fuzzed, mode


def mutate_case(
    base_case: FuzzCase,
    strategy: str,
    rng: random.Random,
    case_index: int,
) -> FuzzCase:
    if strategy not in MUTATION_STRATEGY_NAMES:
        raise ValueError("unknown mutation strategy: %s" % strategy)

    mutated = replace(base_case, data_words=list(base_case.data_words))
    command_target = rng.choice(["cmd1", "cmd2"]) if mutated.is_rt_to_rt else "cmd1"
    original = mutated.cmd2 if command_target == "cmd2" else mutated.cmd1
    if original is None:
        raise ValueError("selected command target is not available")

    detail = ""
    if strategy == "bit_level":
        fuzzed = bit_reverse_range(original, rng=rng)
        detail = "reverse/flip/hybrid"
    elif strategy == "structured":
        fuzzed = structured_fuzz(rng)
        detail = "structured command-field selection"
    else:
        fuzzed, detail = semantic_fuzz_command(original, rng)

    _apply_command(mutated, command_target, fuzzed)
    mutated.strategy = strategy
    mutated.case_id = "%s-%s-%06d" % (mutated.scenario, strategy, case_index)
    mutated.notes = "%s; mutation=%s target=%s" % (
        base_case.notes,
        detail,
        command_target,
    )
    return mutated.normalized()


def _apply_command(case: FuzzCase, target: str, command: int) -> None:
    rt, tx_rx, subaddr, word_count = decode_command_word(command)
    if target == "cmd2":
        case.rt2_addr = rt
        case.rt2_tx_rx = tx_rx
        case.rt2_subaddr = subaddr
        case.rt2_word_count = word_count
        return
    case.rt_addr = rt
    case.tx_rx = tx_rx
    case.subaddr = subaddr
    case.word_count = word_count


def decode_command_word(command: int) -> Tuple[int, int, int, int]:
    value = int(command) & 0xFFFF
    return (
        (value >> 11) & 0x1F,
        (value >> 10) & 0x01,
        (value >> 5) & 0x1F,
        value & 0x1F,
    )
