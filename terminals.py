"""Terminal / connector catalog: which wire sizes each part number accepts."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_CATALOG = Path(__file__).parent / "data" / "terminals.csv"
REQUIRED = ["part_number", "wire_range_awg"]


@dataclass(frozen=True)
class Terminal:
    part_number: str
    description: str
    thickest_awg: int   # smallest AWG number accepted
    thinnest_awg: int   # largest AWG number accepted

    def fits(self, awg: int) -> bool:
        return self.thickest_awg <= awg <= self.thinnest_awg

    @property
    def range_text(self) -> str:
        if self.thickest_awg == self.thinnest_awg:
            return f"{self.thickest_awg}"
        return f"{self.thickest_awg}-{self.thinnest_awg}"


class CatalogError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


def key(part_number: str) -> str:
    """Part numbers match regardless of case and surrounding spaces."""
    return part_number.strip().upper()


def parse_range(text: str) -> tuple[int, int]:
    """'14-16', '16 - 14', '16' or '14 to 16' -> (thickest, thinnest)."""
    nums = [int(n) for n in re.findall(r"\d+", text)]
    if len(nums) not in (1, 2) or not re.fullmatch(r"\s*\d+\s*((-|to|–)\s*\d+\s*)?", text, re.I):
        raise ValueError(f"'{text}' is not a gauge or gauge range like 14-16")
    lo, hi = min(nums), max(nums)
    if hi > 40:
        raise ValueError(f"'{text}' is outside the AWG range")
    return lo, hi


def parse_catalog(f: Iterable[str], source: str = "terminal catalog") -> dict[str, Terminal]:
    reader = csv.DictReader(f)
    if reader.fieldnames is None:
        raise CatalogError([f"{source}: file is empty"])
    headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        raise CatalogError([f"{source}: missing required column(s): {', '.join(missing)}"])

    catalog: dict[str, Terminal] = {}
    problems: list[str] = []
    for row_no, raw in enumerate(reader, start=2):
        row = {k: (raw.get(orig) or "").strip() for k, orig in headers.items()}
        if not any(row.values()):
            continue
        pn = row["part_number"]
        if not pn:
            problems.append(f"{source} row {row_no}: 'part_number' is empty")
            continue
        if key(pn) in catalog:
            problems.append(f"{source} row {row_no}: duplicate part number '{pn}'")
            continue
        try:
            thick, thin = parse_range(row["wire_range_awg"])
        except ValueError as e:
            problems.append(f"{source} row {row_no}: {e}")
            continue
        catalog[key(pn)] = Terminal(pn, row.get("description", ""), thick, thin)

    if problems:
        raise CatalogError(problems)
    return catalog


def load_catalog(path: str | Path = DEFAULT_CATALOG) -> dict[str, Terminal]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return parse_catalog(f, str(Path(path).name))
