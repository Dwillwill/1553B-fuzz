@echo off
setlocal

if "%VENDOR_DIR%"=="" set VENDOR_DIR=..\Windows\DLL\DLL_x64

cl /nologo /EHsc /W4 /LD /DMIL1553_ADAPTER_BUILD_DLL ^
  /I"%VENDOR_DIR%" ^
  mil1553_board_adapter.cpp ^
  /link /OUT:mil1553_board_adapter.dll "%VENDOR_DIR%\mil1553api.lib"

cl /nologo /EHsc /W4 ^
  /DMIL1553_ADAPTER_STATIC ^
  /I"%VENDOR_DIR%" ^
  smoke_bc_once.cpp mil1553_board_adapter.cpp ^
  "%VENDOR_DIR%\mil1553api.lib" ^
  /link /OUT:smoke_bc_once.exe

cl /nologo /EHsc /W4 ^
  /I"%VENDOR_DIR%" ^
  selftest_bc_rt_bm.cpp ^
  "%VENDOR_DIR%\mil1553api.lib" ^
  /link /OUT:selftest_bc_rt_bm.exe

cl /nologo /EHsc /W4 ^
  /I"%VENDOR_DIR%" ^
  bc_send_for_ui_bm.cpp ^
  "%VENDOR_DIR%\mil1553api.lib" ^
  /link /OUT:bc_send_for_ui_bm.exe

endlocal
