# Python Fuzz Engine

This package is the Python side of the 1553B fuzzing tool. It can run without
hardware through the `mock` backend, then switch to the native board adapter on
the deployment Windows machine.

## Dry Run

From the repository root:

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --dry-run --config python\configs\bc_boundary.json --limit 20 --out runs\dryrun.jsonl
```

This only generates cases and writes JSONL records.

## Mock Backend

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --backend mock --config python\configs\bc_boundary.json --limit 20 --out runs\mock.jsonl
```

The mock backend returns deterministic readback-like records. It is useful for
checking case generation, logging, and replay on a laptop.

## Native Backend

Build `board_adapter\mil1553_board_adapter.dll` first, then run:

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --backend native --dll-path board_adapter\mil1553_board_adapter.dll --config python\configs\bc_boundary.json --limit 20 --out runs\native.jsonl
```

The native backend opens the board, resets it, loads one fuzz case at a time
into BC mode, starts the transfer, waits for completion, and stores CDP readback.

## Replay

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner replay --backend mock --input runs\mock.jsonl --case-id cmd_boundary-000000 --out runs\replay.jsonl
```

Use the same command with `--backend native` and `--dll-path` on the board
machine to replay against hardware.

## Current Strategies

- `cmd_boundary`: boundary combinations of RT address, T/R, subaddress, and word count.
- `mode_code`: subaddress 0/31 mode-code cases.
- `broadcast`: broadcast RT address 31 receive cases.
- `rt_to_rt`: RT-to-RT command pairs.
- `data_pattern`: fixed 32-word payload templates.
- `random`: seeded pseudo-random field and payload mutation.
