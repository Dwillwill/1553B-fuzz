from __future__ import annotations

import random
import unittest

from mil1553_fuzz.cases import FuzzCase, make_command_word
from mil1553_fuzz.generation import generate_scenario_fuzz_cases
from mil1553_fuzz.mutations import (
    MUTATION_STRATEGY_NAMES,
    bit_reverse_range,
    semantic_fuzz_command,
    structured_fuzz,
)
from mil1553_fuzz.scenarios import (
    SCENARIO_NAMES,
    ScenarioConfig,
    generate_scenario_cases,
)


class ScenarioGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ScenarioConfig(
            rt_targets=[1],
            subaddresses=[4],
            word_counts=[2],
            rt2_source=2,
            rt3_destination=3,
            delay_100ns=1000,
            seed=7,
        )

    def test_every_scenario_generates_a_baseline_case(self) -> None:
        generated = {
            name: next(generate_scenario_cases(name, self.config))
            for name in SCENARIO_NAMES
        }

        self.assertEqual(set(generated), set(SCENARIO_NAMES))
        for name, case in generated.items():
            self.assertEqual(case.scenario, name)
            self.assertEqual(case.strategy, "baseline")

    def test_mode_command_scenarios_use_expected_command_fields(self) -> None:
        sync_data = next(generate_scenario_cases("bc_rt_sync_data", self.config))
        broadcast_sync_data = next(
            generate_scenario_cases("bc_broadcast_sync_data", self.config)
        )
        broadcast_sync_no_data = next(
            generate_scenario_cases("bc_broadcast_sync_no_data", self.config)
        )
        last_command = next(
            generate_scenario_cases("last_command_readback", self.config)
        )
        query_status = next(
            generate_scenario_cases("bc_query_rt_status", self.config)
        )

        self.assertEqual(sync_data.cmd1, make_command_word(1, 0, 31, 17))
        self.assertEqual(
            broadcast_sync_data.cmd1,
            make_command_word(31, 0, 31, 17),
        )
        self.assertEqual(
            broadcast_sync_no_data.cmd1,
            make_command_word(31, 1, 31, 1),
        )
        self.assertEqual(last_command.cmd1, make_command_word(1, 1, 31, 18))
        self.assertEqual(query_status.cmd1, make_command_word(1, 1, 31, 2))

    def test_rt_to_rt_uses_receiver_then_transmitter_command_order(self) -> None:
        case = next(generate_scenario_cases("rt2_rt3_transfer", self.config))

        self.assertEqual(case.is_rt_to_rt, 1)
        self.assertEqual(case.cmd1, make_command_word(3, 0, 4, 2))
        self.assertEqual(case.cmd2, make_command_word(2, 1, 4, 2))

    def test_round_robin_covers_every_scenario_strategy_pair(self) -> None:
        cases = list(
            generate_scenario_fuzz_cases(
                SCENARIO_NAMES,
                MUTATION_STRATEGY_NAMES,
                self.config,
                len(SCENARIO_NAMES) * len(MUTATION_STRATEGY_NAMES),
            )
        )

        expected = {
            (scenario, strategy)
            for scenario in SCENARIO_NAMES
            for strategy in MUTATION_STRATEGY_NAMES
        }
        self.assertEqual(len(cases), len(expected))
        self.assertEqual(
            {(case.scenario, case.strategy) for case in cases},
            expected,
        )

    def test_generation_is_repeatable_for_the_same_seed(self) -> None:
        first = [
            case.to_dict()
            for case in generate_scenario_fuzz_cases(
                SCENARIO_NAMES,
                MUTATION_STRATEGY_NAMES,
                self.config,
                40,
            )
        ]
        second = [
            case.to_dict()
            for case in generate_scenario_fuzz_cases(
                SCENARIO_NAMES,
                MUTATION_STRATEGY_NAMES,
                self.config,
                40,
            )
        ]

        self.assertEqual(first, second)

    def test_generator_repeats_baselines_until_limit(self) -> None:
        cases = list(
            generate_scenario_fuzz_cases(
                SCENARIO_NAMES,
                MUTATION_STRATEGY_NAMES,
                self.config,
                100,
            )
        )

        self.assertEqual(len(cases), 100)


class MutationTests(unittest.TestCase):
    def test_bit_level_mutation_stays_in_16_bit_range(self) -> None:
        rng = random.Random(11)
        for _ in range(100):
            value = bit_reverse_range(0xA55A, rng=rng)
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 0xFFFF)

    def test_structured_and_semantic_mutations_return_command_words(self) -> None:
        rng = random.Random(13)
        for _ in range(100):
            structured = structured_fuzz(rng)
            semantic, mode = semantic_fuzz_command(0x0822, rng)
            self.assertGreaterEqual(structured, 0)
            self.assertLessEqual(structured, 0xFFFF)
            self.assertGreaterEqual(semantic, 0)
            self.assertLessEqual(semantic, 0xFFFF)
            self.assertIn(
                mode,
                {
                    "word_count_mismatch",
                    "invalid_rt",
                    "invalid_subaddr",
                    "tr_conflict",
                    "broadcast_misuse",
                },
            )

    def test_case_serialization_preserves_scenario_and_old_logs_still_load(self) -> None:
        case = FuzzCase(
            case_id="one",
            scenario="bc_rt_control",
            strategy="bit_level",
            rt_addr=1,
            tx_rx=0,
            subaddr=1,
            word_count=1,
        )
        restored = FuzzCase.from_dict(case.to_dict())
        old_log_case = FuzzCase.from_dict(
            {
                "case_id": "legacy",
                "strategy": "cmd_boundary",
                "rt_addr": 1,
                "tx_rx": 0,
                "subaddr": 1,
                "word_count": 1,
            }
        )

        self.assertEqual(restored.scenario, "bc_rt_control")
        self.assertEqual(old_log_case.scenario, "")


if __name__ == "__main__":
    unittest.main()
