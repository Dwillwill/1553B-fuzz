from __future__ import annotations

import random
from typing import Iterator, List, Sequence, Tuple

from .cases import FuzzCase
from .mutations import MUTATION_STRATEGY_NAMES, mutate_case
from .scenarios import SCENARIO_NAMES, ScenarioConfig, generate_scenario_cases


def generate_scenario_fuzz_cases(
    scenario_names: Sequence[str],
    strategy_names: Sequence[str],
    config: ScenarioConfig,
    limit: int,
) -> Iterator[FuzzCase]:
    if not scenario_names:
        raise ValueError("at least one test scenario is required")
    if not strategy_names:
        raise ValueError("at least one mutation strategy is required")
    unknown_scenarios = sorted(set(scenario_names) - set(SCENARIO_NAMES))
    if unknown_scenarios:
        raise ValueError("unknown scenarios: %s" % ", ".join(unknown_scenarios))
    unknown_strategies = sorted(set(strategy_names) - set(MUTATION_STRATEGY_NAMES))
    if unknown_strategies:
        raise ValueError("unknown mutation strategies: %s" % ", ".join(unknown_strategies))

    config.validate()
    rng = random.Random(config.seed)
    emitted = 0

    while True:
        pending: List[Tuple[str, Iterator[FuzzCase]]] = [
            (name, iter(generate_scenario_cases(name, config)))
            for name in scenario_names
        ]
        pass_start = emitted

        while pending:
            next_round: List[Tuple[str, Iterator[FuzzCase]]] = []
            for name, iterator in pending:
                try:
                    base_case = next(iterator)
                except StopIteration:
                    continue
                next_round.append((name, iterator))
                for strategy in strategy_names:
                    yield mutate_case(base_case, strategy, rng, emitted)
                    emitted += 1
                    if limit > 0 and emitted >= limit:
                        return
            pending = next_round

        if limit <= 0 or emitted == pass_start:
            return
