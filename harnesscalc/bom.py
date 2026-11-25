"""Read and validate a parts BOM (CSV): one row per part that needs a wire."""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REQUIRED = ["part", "current_a", "length_mm"]
OPTIONAL = ["terminals"]
COLUMNS = REQUIRED + OPTIONAL


@dataclass
class Part:
    row: int                 # CSV row number, for error messages
    part: str
    current_a: float
    length_mm: float         # one-way run from the source to the part
    terminals: list[str] = field(default_factory=list)

    @property
    def length_m(self) -> float:
        return self.length_mm / 1000.0


class BomError(ValueError):
    """Raised with every problem found, so the user can fix them in one pass."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


def split_terminals(text: str) -> list[str]:
    """Terminal part numbers are separated by ';' (or '|')."""
    return [t.strip() for t in re.split(r"[;|]", text or "") if t.strip()]


def _num(raw: str, name: str, row: int, problems: list[str]) -> float | None:
    raw = (raw or "").strip()
    if not raw:
        problems.append(f"row {row}: '{name}' is empty")
        return None
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        problems.append(f"row {row}: '{name}' must be a number, got '{raw}'")
        return None
    return value


def parse_bom(f: Iterable[str], source: str = "BOM") -> list[Part]:
    reader = csv.DictReader(f)
    if reader.fieldnames is None:
        raise BomError([f"{source}: file is empty"])
    headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        raise BomError([f"{source}: missing required column(s): {', '.join(missing)}"])

    parts: list[Part] = []
    problems: list[str] = []
    for row_no, raw in enumerate(reader, start=2):  # row 1 is the header
        row = {k: (raw.get(orig) or "").strip() for k, orig in headers.items()}
        if not any(row.values()):
            continue
        if not row["part"]:
            problems.append(f"row {row_no}: 'part' is empty")
        current = _num(row["current_a"], "current_a", row_no, problems)
        if current is not None and current < 0:
            problems.append(f"row {row_no}: 'current_a' cannot be negative")
            current = None
        length = _num(row["length_mm"], "length_mm", row_no, problems)
        if length is not None and length <= 0:
            problems.append(f"row {row_no}: 'length_mm' must be greater than 0")
            length = None
        if row["part"] and current is not None and length is not None:
            parts.append(Part(row_no, row["part"], current, length, split_terminals(row.get("terminals", ""))))

    if problems:
        raise BomError(problems)
    if not parts:
        raise BomError([f"{source}: no parts found"])
    return parts


def read_bom(path: str | Path) -> list[Part]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return parse_bom(f, str(path))
