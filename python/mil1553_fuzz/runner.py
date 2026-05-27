from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Dict, Iterable, List, Optional, Sequence

from .adapters import BoardAdapter
from .cases import FuzzCase, event_record
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
    run_parser.add_argument("--out", default="runs/latest.jsonl")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.set_defaults(func=run_command)

    replay_parser = subparsers.add_parser("replay", help="replay one case from a JSONL run log")
    _add_backend_args(replay_parser)
    replay_parser.add_argument("--input", required=True, help="JSONL run log")
    replay_parser.add_argument("--case-id", required=True)
    replay_parser.add_argument("--timeout-ms", type=int, default=3000)
    replay_parser.add_argument("--out", default="runs/replay.jsonl")
    replay_parser.add_argument("--dry-run", action="store_true")
    replay_parser.set_defaults(func=replay_command)

    args = parser.parse_args(argv)
    return int(args.func(args))


def run_command(args: argparse.Namespace) -> int:
    config_data = _load_json(args.config) if args.config else {}
    seed = int(config_data.get("seed", args.seed))
    config = StrategyConfig.from_dict(config_data, seed=seed)
    strategies = args.strategies or list(config_data.get("strategies", DEFAULT_STRATEGIES))
    cases = list(generate_cases(strategies, config, args.limit))

    _write_records(args.out, _execute_cases(args, cases))
    print("generated=%d output=%s backend=%s dry_run=%s" % (len(cases), args.out, args.backend, args.dry_run))
    return 0


def replay_command(args: argparse.Namespace) -> int:
    case = _find_case(args.input, args.case_id)
    _write_records(args.out, _execute_cases(args, [case]))
    print("replayed=%s output=%s backend=%s dry_run=%s" % (case.case_id, args.out, args.backend, args.dry_run))
    return 0


def _execute_cases(args: argparse.Namespace, cases: Sequence[FuzzCase]) -> Iterable[Dict[str, object]]:
    if args.dry_run:
        for case in cases:
            yield event_record(case, "generated")
        return

    adapter = _make_adapter(args)
    adapter.open()
    try:
        for case in cases:
            readback = adapter.run_case(case, args.timeout_ms)
            yield event_record(case, "executed", readback)
    finally:
        adapter.close()


def _make_adapter(args: argparse.Namespace) -> BoardAdapter:
    if args.backend == "mock":
        return MockAdapter(channel=args.channel)
    if args.backend == "native":
        return CtypesAdapter(
            dll_path=args.dll_path or default_adapter_path(),
            card_index=args.card_index,
            channel=args.channel,
            timeout_ms=args.timeout_ms,
        )
    raise ValueError("unknown backend: %s" % args.backend)


def _write_records(path: str, records: Iterable[Dict[str, object]]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fp:
        for record in records:
            fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            fp.write("\n")


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
