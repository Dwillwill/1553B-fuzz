# MIL-STD-1553B Board Adapter

This directory contains a thin C ABI wrapper around the vendor `mil1553api`
library. It is intended to be called by a Python fuzz engine through `ctypes`
or by a small CLI smoke test.

## Files

- `mil1553_board_adapter.h`: exported C ABI and fuzz case structs.
- `mil1553_board_adapter.cpp`: BC-mode board adapter implementation.
- `smoke_bc_once.cpp`: sends one BC-to-RT message and prints readback fields.
- `bc_send_for_ui_bm.cpp`: sends repeated BC messages without reset so a vendor UI BM can monitor them.
- `selftest_bc_rt_bm.cpp`: initializes BC, RT, and BM in one process for single-channel multifunction self-test.
- `Makefile`: Linux build using `../Linux/SO/libmil1553api.so`.
- `build_windows_x64.bat`: Windows x64 build using `../Windows/DLL/DLL_x64`.

## Current Scope

Implemented:

- device open/close/reset
- BC mode prepare
- load one or more fuzz cases into BCCB/CDP entries
- start/stop/wait for BC execution
- read back CDP result fields

Not implemented yet:

- RT fault simulation
- BM readout
- direct fault injection controls
- JSON parsing or fuzz algorithm logic

## Linux Build

```sh
cd board_adapter
make
make smoke
LD_LIBRARY_PATH=../Linux/SO:. ./smoke_bc_once 0 0
```

Arguments for `smoke_bc_once`:

```text
smoke_bc_once [card_index] [channel]
```

## Windows x64 Build

Run from a Visual Studio Developer Command Prompt:

```bat
cd board_adapter
build_windows_x64.bat
copy ..\Windows\DLL\DLL_x64\mil1553api.dll .
smoke_bc_once.exe 0 0
bc_send_for_ui_bm.exe 0 0 1 1 10 1000 A
selftest_bc_rt_bm.exe 0 0
```

## Fuzz Case Notes

`Mil1553FuzzCase.next_msg_num == 0` means "auto-link to the next case". For the
last case, auto-link becomes `NO_NEXT`. If you need an explicit branch or loop,
set `next_msg_num` yourself after we add branch-control fields to the adapter.

`word_count == 0` follows 1553 convention through the vendor API: it represents
32 data words for ordinary data transfer commands.
