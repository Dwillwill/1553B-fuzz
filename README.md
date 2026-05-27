# 1553B Fuzz

Early-stage MIL-STD-1553B fuzzing tooling.

This repository currently contains a thin C/C++ board adapter for the vendor
1553B card API. The adapter is designed to be called later from a Python fuzz
engine through `ctypes` or from small native smoke-test programs.

## Repository Scope

Included:

- `board_adapter/`: C ABI wrapper around the vendor `mil1553api` library.
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

Planned:

- Python `ctypes` binding
- command-word boundary fuzzing
- mode-code fuzzing
- sequence insertion fuzzing
- RT fault simulation
