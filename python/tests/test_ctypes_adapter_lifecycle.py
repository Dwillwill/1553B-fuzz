from __future__ import annotations

import ctypes
import unittest
from collections import Counter
from unittest.mock import patch

from mil1553_fuzz.cases import FuzzCase
from mil1553_fuzz.ctypes_adapter import CtypesAdapter


class FakeFunction:
    def __init__(self, name: str, calls: Counter[str], callback=None) -> None:
        self.name = name
        self.calls = calls
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls[self.name] += 1
        if self.callback is not None:
            return self.callback(*args)
        return 0


class FakeLibrary:
    FUNCTION_NAMES = [
        "mil1553_adapter_create",
        "mil1553_adapter_destroy",
        "mil1553_adapter_open",
        "mil1553_adapter_reset",
        "mil1553_adapter_bc_prepare",
        "mil1553_adapter_bc_load_cases",
        "mil1553_adapter_bc_start",
        "mil1553_adapter_bc_wait_done",
        "mil1553_adapter_request_stop",
        "mil1553_adapter_bc_stop",
        "mil1553_adapter_bc_readback",
        "mil1553_adapter_last_vendor_status",
    ]

    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        for name in self.FUNCTION_NAMES:
            callback = self._create_adapter if name == "mil1553_adapter_create" else None
            setattr(self, name, FakeFunction(name, self.calls, callback))

    @staticmethod
    def _create_adapter(out_adapter) -> int:
        ctypes.cast(out_adapter, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(1)
        return 0


class CtypesAdapterLifecycleTests(unittest.TestCase):
    def test_prepare_once_and_request_stop_without_vendor_stop(self) -> None:
        library = FakeLibrary()
        with patch("mil1553_fuzz.ctypes_adapter._load_library", return_value=library):
            adapter = CtypesAdapter("unused.dll")
            adapter.open()
            adapter.run_case(FuzzCase("one", "test", 1, 0, 1, 1), 100)
            adapter.run_case(FuzzCase("two", "test", 1, 0, 1, 1), 100)
            adapter.stop()
            adapter.close()

        self.assertEqual(library.calls["mil1553_adapter_bc_prepare"], 1)
        self.assertEqual(library.calls["mil1553_adapter_bc_load_cases"], 2)
        self.assertEqual(library.calls["mil1553_adapter_request_stop"], 1)
        self.assertEqual(library.calls["mil1553_adapter_bc_stop"], 0)


if __name__ == "__main__":
    unittest.main()
