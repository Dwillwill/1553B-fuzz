from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from .cases import FuzzCase, Readback


class BoardAdapter(ABC):
    @abstractmethod
    def open(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def run_case(self, case: FuzzCase, timeout_ms: int) -> Readback:
        raise NotImplementedError

    def stop(self) -> None:
        """Request an active hardware operation to stop."""

    def run_cases(self, cases: Sequence[FuzzCase], timeout_ms: int) -> Sequence[Readback]:
        return [self.run_case(case, timeout_ms) for case in cases]


class AdapterError(RuntimeError):
    pass
