# 1553B Fuzz

Early-stage MIL-STD-1553B fuzzing tooling.

This repository currently contains:

- a thin C/C++ board adapter for the vendor 1553B card API
- a Python fuzz runner with offline `mock` execution and native `ctypes` support

## Repository Scope

Included:

- `board_adapter/`: C ABI wrapper around the vendor `mil1553api` library.
- `python/`: Python fuzz case generation, mock backend, native backend, and replay tooling.
- `.gitignore`: excludes vendor delivery materials and local build outputs.

Not included:

- vendor documents
- vendor examples
- board drivers
- `mil1553api.dll`
- `mil1553api.lib`
- `libmil1553api.so`
- board installation packages

Keep those files in the local vendor delivery directory only.

## Windows Build

From a Visual Studio Developer Command Prompt:

```bat
cd board_adapter
set VENDOR_DIR=..\Windows\DLL\DLL_x64
build_windows_x64.bat
copy %VENDOR_DIR%\mil1553api.dll .
smoke_bc_once.exe 0 0
```

If the vendor SDK is somewhere else, set `VENDOR_DIR` to that directory before
running the build script.

## Current Status

Implemented:

- device open/close/reset
- BC mode prepare
- load one or more fuzz cases into BCCB/CDP entries
- start/stop/wait for BC execution
- read back CDP result fields
- Python fuzz case model
- nine independent 1553B business test scenarios
- bit-level command-word mutation
- structured command-field mutation
- semantic-sensitive command mutation
- JSONL run logs
- case replay
- offline mock backend
- native `ctypes` backend

Python dry run:

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --dry-run --config python\configs\scenario_campaign.json --limit 30 --out runs\dryrun.jsonl
```

Python mock execution:

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --backend mock --config python\configs\scenario_campaign.json --limit 30 --out runs\mock.jsonl
```

Python GUI:

```bat
run_fuzz_gui.bat
```

The default GUI is a local Web workspace served only on `127.0.0.1`. All HTML,
CSS, and JavaScript assets are included in the project, so it works on the
offline board machine without Node.js, a package installation, or internet
access. The original Tkinter interface remains available through:

```bat
run_fuzz_tk.bat
```

## Offline Board Machine Deployment

The board machine only needs Python 3.10+ and the installed vendor driver.
Visual Studio is not required at runtime. Copy the whole project directory and
keep this relative layout:

```text
1553B-fuzz\
  run_fuzz_gui.bat
  python\
  board_adapter\
    mil1553_board_adapter.dll
    mil1553api.dll
    smoke_bc_once.exe
    selftest_bc_rt_bm.exe
    bc_send_for_ui_bm.exe
```

Start the GUI from the project root:

```bat
run_fuzz_gui.bat
```

The default adapter path is relative to the project root:

```text
board_adapter\mil1553_board_adapter.dll
```

The GUI provides a `停止测试` button. Closing the window during a campaign
first requests `BCStop`, waits for the worker thread to release the adapter,
and only then exits.

If Windows reports a driver blue screen, stop board testing and run
`collect_bsod_diagnostics.bat` as administrator after rebooting. The script
does not call the board API. It records relevant driver/device information and
copies the newest minidump into the local `diagnostics` directory. Do not
publish that directory to a public repository.

Native execution on the board machine:

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --backend native --dll-path board_adapter\mil1553_board_adapter.dll --config python\configs\scenario_campaign.json --limit 30 --interval-ms 200 --bus A --out runs\native.jsonl
```

If a vendor UI is already using BM on the same machine, use `--no-reset` so the
fuzz runner does not clear the UI-side monitor setup:

```bat
set PYTHONPATH=python
python -m mil1553_fuzz.runner run --backend native --no-reset --dll-path board_adapter\mil1553_board_adapter.dll --scenario bc_rt_control --scenario rt_bc_data_report --strategy bit_level --strategy semantic --limit 100 --interval-ms 200 --bus A --out runs\native_ui_bm.jsonl
```

Planned:

- sequence insertion fuzzing
- RT fault simulation
- result analysis and triage summaries
