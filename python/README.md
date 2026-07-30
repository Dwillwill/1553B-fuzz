# Python Fuzz Engine

This package is the Python side of the 1553B fuzzing tool. It can run without
hardware through the `mock` backend, then switch to the native board adapter on
the deployment Windows machine.

## Dry Run

From the repository root:

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --dry-run --config python\configs\scenario_campaign.json --limit 30 --out runs\dryrun.jsonl
```

This only generates cases and writes JSONL records.

## Mock Backend

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --backend mock --config python\configs\scenario_campaign.json --limit 30 --out runs\mock.jsonl
```

The mock backend returns deterministic readback-like records. It is useful for
checking case generation, logging, and replay on a laptop.

## Native Backend

Build `board_adapter\mil1553_board_adapter.dll` first, then run:

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --backend native --dll-path board_adapter\mil1553_board_adapter.dll --config python\configs\scenario_campaign.json --limit 30 --interval-ms 200 --bus A --out runs\native.jsonl
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

## GUI

From the repository root:

```bat
run_fuzz_gui.bat
```

The GUI uses the same case generator and adapters as the command line runner.
Use `模拟后端` for laptop testing and `真实板卡` on the board machine. The board
machine needs Python 3.10+ and the vendor driver, but does not need Visual
Studio. Keep `python`, `board_adapter`, and `run_fuzz_gui.bat` in their original
relative locations when copying the project.

The GUI is localized in Chinese and supports safe cancellation. `停止测试` sets
a campaign cancellation event and calls the native adapter's `BCStop`. Closing
the window while a campaign is active follows the same stop-and-wait process.

For the use case where the vendor UI is already running BM, enable `No reset on
open` in the GUI. This avoids clearing the UI-side BM setup before sending BC
fuzz cases.

## Test Scenarios

- `bc_rt_control`: BC sends a control/data message to one RT.
- `bc_rt_sync_data`: unicast Synchronize With Data mode command.
- `bc_broadcast_data`: BC broadcasts ordinary data.
- `bc_broadcast_sync_data`: broadcast Synchronize With Data mode command.
- `bc_broadcast_sync_no_data`: broadcast Synchronize mode command without data.
- `rt2_rt3_transfer`: BC schedules RT2 to transmit data to RT3.
- `last_command_readback`: BC requests the RT's last received command.
- `bc_query_rt_status`: BC requests the RT status word.
- `rt_bc_data_report`: BC requests ordinary data from an RT.

For `rt2_rt3_transfer`, the adapter writes the receiver command to `CMD1` and
the transmitter command to `CMD2`, matching the vendor API's RT-to-RT message
layout. The business data direction is still RT2 to RT3.

## Mutation Strategies

- `bit_level`: randomly reverse, flip, or reverse-and-flip command-word bits.
- `structured`: choose RT, T/R, subaddress, and word-count values from boundary
  and protocol-relevant sets.
- `semantic`: introduce word-count mismatch, RT/subaddress misuse, T/R conflict,
  or broadcast misuse.

Scenarios and mutation strategies are selected independently. A generated case
records both names in JSONL, so BM observations can be correlated with the
business scenario and the mutation that produced the command word.

The older strategies in `configs\bc_boundary.json` remain available to preserve
existing command-line campaigns and replay logs, but they are no longer shown
in the GUI.
