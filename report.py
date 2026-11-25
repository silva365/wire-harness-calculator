"""Format sizing results as a terminal table, Markdown and CSV."""

from __future__ import annotations

import csv
import io

from .sizing import Config, Result


def _range(r: tuple[int, int] | None) -> str:
    if r is None:
        return ""
    return f"{r[0]}" if r[0] == r[1] else f"{r[0]}-{r[1]}"


def _n(x: float | None, d: int) -> str:
    return "" if x is None else f"{x:.{d}f}"


def settings_line(cfg: Config) -> str:
    ret = "round trip (return wire)" if cfg.round_trip else "one way (chassis return)"
    return (f"{cfg.supply_voltage:g} V supply · max drop {cfg.max_drop_pct:g}% · "
            f"ambient {cfg.ambient_c:g} C · thinnest AWG {cfg.thinnest_awg} · length {ret}")


def render_text(results: list[Result], cfg: Config) -> str:
    rows = [("PART", "LOAD A", "LENGTH mm", "TERMINALS", "AWG", "SET BY", "DROP %", "STATUS")]
    for r in results:
        rows.append((
            r.part.part, f"{r.part.current_a:g}", f"{r.part.length_mm:g}", "; ".join(r.part.terminals) or "-",
            str(r.awg) if r.awg is not None else "-", r.limited_by, _n(r.drop_pct, 2) or "-",
            "OK" if r.ok else "CHECK",
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = [settings_line(cfg), ""]
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip() for row in rows]
    notes = [(r.part.part, n) for r in results for n in r.notes]
    if notes:
        lines += ["", "Notes:"] + [f"  {who}: {n}" for who, n in notes]
    return "\n".join(lines)


def render_markdown(results: list[Result], cfg: Config, title: str) -> str:
    bad = sum(not r.ok for r in results)
    lines = [
        f"# Wire gauges: {title}",
        "",
        f"**{len(results) - bad} of {len(results)} parts sized**" + (f", **{bad} need attention**" if bad else ""),
        "",
        settings_line(cfg),
        "",
        "| Part | Load (A) | Length (mm) | Terminals | Wire AWG | Set by | Terminal range | Drop (%) | Status |",
        "|---|---:|---:|---|---:|---|---|---:|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.part.part} | {r.part.current_a:g} | {r.part.length_mm:g} | {'; '.join(r.part.terminals)} | "
            f"{r.awg if r.awg is not None else '—'} | {r.limited_by} | {_range(r.terminal_range)} | "
            f"{_n(r.drop_pct, 2)} | {'OK' if r.ok else '**CHECK**'} |"
        )
    notes = [(r.part.part, n) for r in results for n in r.notes]
    if notes:
        lines += ["", "## Notes", ""] + [f"- **{who}**: {n}" for who, n in notes]
    lines += [
        "",
        "---",
        "Wire data are typical SAE J1128 TXL values; terminal ranges come from the terminal catalog. "
        "Verify both against manufacturer datasheets.",
        "",
    ]
    return "\n".join(lines)


def render_csv(results: list[Result]) -> str:
    f = io.StringIO()
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["part", "current_a", "length_mm", "terminals", "awg", "electrical_min_awg", "set_by",
                "terminal_range_awg", "ampacity_a", "drop_v", "drop_pct", "status", "notes"])
    for r in results:
        w.writerow([
            r.part.part, f"{r.part.current_a:g}", f"{r.part.length_mm:g}", "; ".join(r.part.terminals),
            r.awg if r.awg is not None else "", r.electrical_awg if r.electrical_awg is not None else "",
            r.limited_by, _range(r.terminal_range), _n(r.ampacity_a, 1), _n(r.drop_v, 3), _n(r.drop_pct, 2),
            "OK" if r.ok else "CHECK", " | ".join(r.notes),
        ])
    return f.getvalue()
