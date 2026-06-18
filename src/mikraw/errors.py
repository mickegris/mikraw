"""Typed errors and per-file result types for mikraw."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MikrawError(Exception):
    """Base class for mikraw errors."""


class DecodeError(MikrawError):
    """RAW file could not be decoded by LibRaw/rawpy."""


class Status(str, Enum):
    CONVERTED = "converted"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class FileResult:
    """Outcome of processing a single input file."""

    source: str
    output: str | None
    status: Status
    message: str = ""
