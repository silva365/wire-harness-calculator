"""Pick the wire gauge for each part on the BOM.

For every part:
  1. Electrical minimum: the thinnest wire that carries the part's current and
     keeps the voltage drop within the limit.
  2. Terminal fit: the gauges every listed terminal accepts.
  3. Result: the thinnest gauge that satisfies both. If the terminals force a
     thicker wire, that is noted; if no gauge satisfies both, the part fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import calcs
from .bom import Part
from .tables import GAUGES_THIN_TO_THICK, WIRE_TABLE
from .terminals import Terminal, key


@dataclass
class Config:
    supply_voltage: float = 12.0
    max_drop_pct: float = 5.0
    ambient_c: float = 30.0
    thinnest_awg: int = 22        # mechanical minimum for harness wire
    round_trip: bool = True       # return wire runs the same length back

    def problems(self) -> list[str]:
        out = []
        if self.supply_voltage <= 0:
            out.append("supply voltage must be greater than 0")
        if self.max_drop_pct <= 0:
            out.append("max voltage drop must be greater than 0%")
        if calcs.ambient_factor(self.ambient_c) <= 0:
            out.append("ambient temperature must be below the 125 C insulation rating")
        if self.thinnest_awg not in WIRE_TABLE:
            out.append(f"thinnest gauge must be one of {', '.join(map(str, GAUGES_THIN_TO_THICK))}")
        return out


@dataclass
class Result:
    part: Part
    awg: int | None                       # the answer
    electrical_awg: int | None            # what current + drop alone need
    limited_by: str                       # "current", "voltage drop", "minimum gauge", "terminal"
    terminal_range: tuple[int, int] | None = None   # (thickest, thinnest) all terminals accept
    ampacity_a: float | None = None
    drop_v: float | None = None
    drop_pct: float | None = None
    notes: list[str] = field(default_factory=list)
    ok: bool = True


def _fmt_range(r: tuple[int, int]) -> str:
    return f"{r[0]}" if r[0] == r[1] else f"{r[0]}-{r[1]}"


def size_part(p: Part, cfg: Config, catalog: dict[str, Terminal]) -> Result:
    wire_len = p.length_m * (2 if cfg.round_trip else 1)
    max_drop_v = cfg.supply_voltage * cfg.max_drop_pct / 100.0

    elec, limited_by = calcs.electrical_minimum(
        p.current_a, wire_len, max_drop_v, cfg.ambient_c, cfg.thinnest_awg
    )
    res = Result(part=p, awg=None, electrical_awg=elec, limited_by=limited_by)

    if elec is None:
        res.ok = False
        res.notes.append(
            f"no gauge up to AWG {GAUGES_THIN_TO_THICK[-1]} meets the {limited_by} requirement; "
            "split the load or shorten the run"
        )

    # Terminal compatibility.
    terms: list[Terminal] = []
    unknown = []
    for pn in p.terminals:
        t = catalog.get(key(pn))
        (terms.append(t) if t else unknown.append(pn))
    if unknown:
        res.ok = False
        res.notes.append(f"not in terminal catalog: {', '.join(unknown)}")
    if terms:
        thick = max(t.thickest_awg for t in terms)
        thin = min(t.thinnest_awg for t in terms)
        if thick > thin:
            res.ok = False
            res.notes.append(
                "terminals share no wire size: "
                + ", ".join(f"{t.part_number} takes {t.range_text}" for t in terms)
            )
            return res
        res.terminal_range = (thick, thin)

    if elec is None:
        return res

    # Thinnest gauge that is thick enough electrically and fits the terminals.
    lo, hi = res.terminal_range or (0, 99)
    choices = [g for g in GAUGES_THIN_TO_THICK if g <= elec and lo <= g <= hi]
    if not choices:
        res.ok = False
        names = ", ".join(t.part_number for t in terms)
        res.notes.append(
            f"needs AWG {elec} or thicker, but {names} only take{'s' if len(terms) == 1 else ''} "
            f"AWG {_fmt_range(res.terminal_range)}; choose a terminal rated for AWG {elec}"
        )
        return res

    res.awg = choices[0]
    if res.awg != elec:
        res.limited_by = "terminal"
        res.notes.append(f"AWG {elec} is enough electrically; AWG {res.awg} is the thinnest the terminal accepts")

    res.ampacity_a = calcs.ampacity(res.awg, cfg.ambient_c)
    res.drop_v = calcs.voltage_drop(res.awg, p.current_a, wire_len, cfg.ambient_c)
    res.drop_pct = 100.0 * res.drop_v / cfg.supply_voltage
    return res


def size_bom(parts: list[Part], cfg: Config, catalog: dict[str, Terminal]) -> list[Result]:
    return [size_part(p, cfg, catalog) for p in parts]
