from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Dict, Optional, Sequence

from .adapters import BoardAdapter
from .cases import FuzzCase
from .campaign import apply_bus, repeat_cases, run_campaign, write_dry_run
from .ctypes_adapter import CtypesAdapter, default_adapter_path
from .mock_adapter import MockAdapter
from .strategies import StrategyConfig, generate_cases


DEFAULT_STRATEGIES = ["cmd_boundary", "mode_code", "broadcast", "rt_to_rt", "data_pattern"]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIL-STD-1553B fuzz runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="generate and run fuzz cases")
    _add_backend_args(run_parser)
    run_parser.add_argument("--config", help="JSON campaign config")
    run_parser.add_argument("--strategy", action="append", dest="strategies")
    run_parser.add_argument("--limit", type=int, default=20)
    run_parser.add_argument("--seed", type=int, default=1)
    run_parser.add_argument("--timeout-ms", type=int, default=3000)
    run_parser.add_argument("--interval-ms", type=int, default=0)
    run_parser.add_argument("--repeat-each", type=int, default=1)
    run_parser.add_argument("--bus", choices=["A", "B"], default="A")
    run_parser.add_argument("--out", default="runs/latest.jsonl")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--no-reset", action="store_true")
    run_parser.set_defaults(func=run_command)

    replay_parser = subparsers.add_parser("replay", help="replay one case from a JSONL run log")
    _add_backend_args(replay_parser)
    replay_parser.add_argument("--input", required=True, help="JSONL run log")
    replay_parser.add_argument("--case-id", required=True)
    replay_parser.add_argument("--timeout-ms", type=int, default=3000)
    replay_parser.add_argument("--interval-ms", type=int, default=0)
    replay_parser.add_argument("--repeat-each", type=int, default=1)
    replay_parser.add_argument("--bus", choices=["A", "B"], default="A")
    replay_parser.add_argument("--out", default="runs/replay.jsonl")
    replay_parser.add_argument("--dry-run", action="store_true")
    replay_parser.add_argument("--no-reset", action="store_true")
    replay_parser.set_defaults(func=replay_command)

    args = parser.parse_args(argv)
    return int(args.func(args))


def run_command(args: argparse.Namespace) -> int:
    config_data = _load_json(args.config) if args.config else {}
    seed = int(config_data.get("seed", args.seed))
    config = StrategyConfig.from_dict(config_data, seed=seed)
    strategies = args.strategies or list(config_data.get("strategies", DEFAULT_STRATEGIES))
    cases = _prepare_cases(list(generate_cases(strategies, config, args.limit)), args)

    _execute_or_write(args, cases)
    print("generated=%d output=%s backend=%s dry_run=%s" % (len(cases), args.out, args.backend, args.dry_run))
    return 0


def replay_command(args: argparse.Namespace) -> int:
    case = _prepare_cases([_find_case(args.input, args.case_id)], args)[0]
    _execute_or_write(args, [case])
    print("replayed=%s output=%s backend=%s dry_run=%s" % (case.case_id, args.out, args.backend, args.dry_run))
    return 0


def _prepare_cases(cases: Sequence[FuzzCase], args: argparse.Namespace) -> Sequence[FuzzCase]:
    return list(repeat_cases(list(apply_bus(cases, args.bus)), args.repeat_each))


def _execute_or_write(args: argparse.Namespace, cases: Sequence[FuzzCase]) -> None:
    if args.dry_run:
        write_dry_run(cases, args.out)
        return

    adapter = _make_adapter(args)
    run_campaign(
        adapter=adapter,
        cases=cases,
        timeout_ms=args.timeout_ms,
        interval_ms=args.interval_ms,
        out_path=args.out,
    )


def _make_adapter(args: argparse.Namespace) -> BoardAdapter:
    if args.backend == "mock":
        return MockAdapter(channel=args.channel)
    if args.backend == "native":
        return CtypesAdapter(
            dll_path=args.dll_path or default_adapter_path(),
            card_index=args.card_index,
            channel=args.channel,
            timeout_ms=args.timeout_ms,
            reset_on_open=not args.no_reset,
        )
    raise ValueError("unknown backend: %s" % args.backend)


def _find_case(path: str, case_id: str) -> FuzzCase:
    with Path(path).open("r", encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            record = json.loads(line)
            case_data = record.get("case", {})
            if case_data.get("case_id") == case_id:
                return FuzzCase.from_dict(case_data)
    raise SystemExit("case_id not found: %s" % case_id)


def _load_json(path: str) -> Dict[str, object]:
    with Path(path).open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    return data


def _add_backend_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--backend", choices=["mock", "native"], default="mock")
    parser.add_argument("--dll-path", help="path to mil1553_board_adapter.dll/.so")
    parser.add_argument("--card-index", type=int, default=0)
    parser.add_argument("--channel", type=int, default=0)


if __name__ == "__main__":
    sys.exit(main())
