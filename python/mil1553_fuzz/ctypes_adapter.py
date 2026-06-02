from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys
from typing import Optional

from .adapters import AdapterError, BoardAdapter
from .cases import DATA_WORDS, FuzzCase, Readback


ADAPTER_OK = 0


class NativeFuzzCase(ctypes.Structure):
    _fields_ = [
        ("rt_addr", ctypes.c_uint8),
        ("tx_rx", ctypes.c_uint8),
        ("subaddr", ctypes.c_uint8),
        ("word_count", ctypes.c_uint8),
        ("is_rt_to_rt", ctypes.c_uint8),
        ("rt2_addr", ctypes.c_uint8),
        ("rt2_tx_rx", ctypes.c_uint8),
        ("rt2_subaddr", ctypes.c_uint8),
        ("rt2_word_count", ctypes.c_uint8),
        ("bcmsg_fmt", ctypes.c_uint32),
        ("bcmsg_rty", ctypes.c_uint32),
        ("delay_100ns", ctypes.c_uint32),
        ("sched_time_100ns", ctypes.c_uint32),
        ("frame_time_100ns", ctypes.c_uint32),
        ("next_msg_num", ctypes.c_uint32),
        ("data_words", ctypes.c_uint32 * DATA_WORDS),
    ]


class NativeReadback(ctypes.Structure):
    _fields_ = [
        ("cdp_sts", ctypes.c_uint32),
        ("time_tag_h", ctypes.c_uint32),
        ("time_tag_l", ctypes.c_uint32),
        ("cmd1", ctypes.c_uint32),
        ("cmd2", ctypes.c_uint32),
        ("rt_sts1", ctypes.c_uint32),
        ("rt_sts2", ctypes.c_uint32),
        ("msg_data", ctypes.c_uint32 * DATA_WORDS),
    ]


class CtypesAdapter(BoardAdapter):
    def __init__(
        self,
        dll_path: str,
        card_index: int = 0,
        channel: int = 0,
        timeout_ms: int = 3000,
        reset_on_open: bool = True,
    ) -> None:
        self.dll_path = str(Path(dll_path))
        self.card_index = card_index
        self.channel = channel
        self.timeout_ms = timeout_ms
        self.reset_on_open = reset_on_open
        self._lib = _load_library(self.dll_path)
        self._adapter = ctypes.c_void_p()
        self._opened = False
        self._bind_functions()

    def open(self) -> None:
        self._check(self._lib.mil1553_adapter_create(ctypes.byref(self._adapter)), "create")
        self._check(
            self._lib.mil1553_adapter_open(self._adapter, self.card_index, self.channel),
            "open",
        )
        self._opened = True
        if self.reset_on_open:
            self._check(self._lib.mil1553_adapter_reset(self._adapter), "reset")

    def close(self) -> None:
        if self._adapter:
            self._lib.mil1553_adapter_destroy(self._adapter)
        self._adapter = ctypes.c_void_p()
        self._opened = False

    def run_case(self, case: FuzzCase, timeout_ms: int) -> Readback:
        if not self._opened:
            raise AdapterError("native adapter is not open")

        native_case = _to_native_case(case)
        native_readback = NativeReadback()
        self._check(self._lib.mil1553_adapter_bc_prepare(self._adapter, 1, 0), "bc_prepare")
        self._check(
            self._lib.mil1553_adapter_bc_load_cases(
                self._adapter,
                ctypes.byref(native_case),
                1,
            ),
            "bc_load_cases",
        )
        self._check(self._lib.mil1553_adapter_bc_start(self._adapter, 0), "bc_start")
        wait_timeout = timeout_ms if timeout_ms > 0 else self.timeout_ms
        self._check(
            self._lib.mil1553_adapter_bc_wait_done(self._adapter, wait_timeout),
            "bc_wait_done",
        )
        self._check(
            self._lib.mil1553_adapter_bc_readback(
                self._adapter,
                0,
                ctypes.byref(native_readback),
            ),
            "bc_readback",
        )
        return _from_native_readback(native_readback)

    def _bind_functions(self) -> None:
        self._lib.mil1553_adapter_create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self._lib.mil1553_adapter_create.restype = ctypes.c_uint32
        self._lib.mil1553_adapter_destroy.argtypes = [ctypes.c_void_p]
        self._lib.mil1553_adapter_destroy.restype = ctypes.c_uint32
        self._lib.mil1553_adapter_open.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint8,
            ctypes.c_uint8,
        ]
        self._lib.mil1553_adapter_open.restype = ctypes.c_uint32
        self._lib.mil1553_adapter_reset.argtypes = [ctypes.c_void_p]
        self._lib.mil1553_adapter_reset.restype = ctypes.c_uint32
        self._lib.mil1553_adapter_bc_prepare.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint16,
        ]
        self._lib.mil1553_adapter_bc_prepare.restype = ctypes.c_uint32
        self._lib.mil1553_adapter_bc_load_cases.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(NativeFuzzCase),
            ctypes.c_uint32,
        ]
        self._lib.mil1553_adapter_bc_load_cases.restype = ctypes.c_uint32
        self._lib.mil1553_adapter_bc_start.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self._lib.mil1553_adapter_bc_start.restype = ctypes.c_uint32
        self._lib.mil1553_adapter_bc_wait_done.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self._lib.mil1553_adapter_bc_wait_done.restype = ctypes.c_uint32
        self._lib.mil1553_adapter_bc_readback.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.POINTER(NativeReadback),
        ]
        self._lib.mil1553_adapter_bc_readback.restype = ctypes.c_uint32
        self._lib.mil1553_adapter_last_vendor_status.argtypes = [ctypes.c_void_p]
        self._lib.mil1553_adapter_last_vendor_status.restype = ctypes.c_uint32

    def _check(self, status: int, step: str) -> None:
        if status == ADAPTER_OK:
            return
        vendor = 0
        if self._adapter:
            vendor = self._lib.mil1553_adapter_last_vendor_status(self._adapter)
        raise AdapterError(
            "%s failed: adapter_status=0x%08x vendor_status=0x%08x"
            % (step, status, vendor)
        )


def default_adapter_path() -> str:
    root = Path(__file__).resolve().parents[2]
    if sys.platform.startswith("win"):
        return str(root / "board_adapter" / "mil1553_board_adapter.dll")
    return str(root / "board_adapter" / "libmil1553_board_adapter.so")


def _load_library(path: str) -> ctypes.CDLL:
    if sys.platform.startswith("win"):
        if hasattr(os, "add_dll_directory"):
            dll_dir = str(Path(path).resolve().parent)
            os.add_dll_directory(dll_dir)
        return ctypes.WinDLL(path)
    return ctypes.CDLL(path)


def _to_native_case(case: FuzzCase) -> NativeFuzzCase:
    normalized = case.normalized()
    words = (ctypes.c_uint32 * DATA_WORDS)(*normalized.data_words)
    return NativeFuzzCase(
        normalized.rt_addr,
        normalized.tx_rx,
        normalized.subaddr,
        normalized.word_count,
        normalized.is_rt_to_rt,
        normalized.rt2_addr,
        normalized.rt2_tx_rx,
        normalized.rt2_subaddr,
        normalized.rt2_word_count,
        normalized.bcmsg_fmt,
        normalized.bcmsg_rty,
        normalized.delay_100ns,
        normalized.sched_time_100ns,
        normalized.frame_time_100ns,
        normalized.next_msg_num,
        words,
    )


def _from_native_readback(readback: NativeReadback) -> Readback:
    return Readback(
        cdp_sts=readback.cdp_sts,
        time_tag_h=readback.time_tag_h,
        time_tag_l=readback.time_tag_l,
        cmd1=readback.cmd1,
        cmd2=readback.cmd2,
        rt_sts1=readback.rt_sts1,
        rt_sts2=readback.rt_sts2,
        msg_data=list(readback.msg_data),
    )
