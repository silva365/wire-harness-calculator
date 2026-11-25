"""JSON-in, JSON-out entry points for the web GUI.

The browser runs this same Python package (via Pyodide), so the GUI and the
CLI share one implementation.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import math

from .bom import COLUMNS, REQUIRED, BomError, parse_bom
from .report import render_csv, render_markdown
from .sizing import Config, size_bom
from .tables import GAUGES_THIN_TO_THICK
from .terminals import CatalogError, parse_catalog


def info() -> str:
    return json.dumps({
        "columns": COLUMNS,
        "required": REQUIRED,
        "gauges": GAUGES_THIN_TO_THICK,
        "defaults": dataclasses.asdict(Config()),
    })


def csv_to_rows(text: str) -> str:
    """Parse BOM CSV text into editor rows (known columns only)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        return json.dumps({"rows": [], "ignored": []})
    headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    ignored = [orig for low, orig in headers.items() if low not in COLUMNS]
    rows = []
    for raw in reader:
        row = {c: (raw.get(headers[c]) or "").strip() if c in headers else "" for c in COLUMNS}
        if any(row.values()):
            rows.append(row)
    return json.dumps({"rows": rows, "ignored": ignored})


def rows_to_csv(rows_json: str) -> str:
    f = io.StringIO()
    w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in json.loads(rows_json):
        w.writerow({c: r.get(c, "") for c in COLUMNS})
    return f.getvalue()


def catalog(text: str) -> str:
    """Parse a terminal catalog for display; reports problems instead of raising."""
    try:
        cat = parse_catalog(io.StringIO(text.lstrip("﻿")))
    except CatalogError as e:
        return json.dumps({"ok": False, "problems": e.problems})
    return json.dumps({"ok": True, "terminals": [
        {"part_number": t.part_number, "description": t.description, "range": t.range_text}
        for t in cat.values()
    ]})


def _config(raw: dict) -> Config:
    cfg = Config()
    for name in ("supply_voltage", "max_drop_pct", "ambient_c", "thinnest_awg"):
        if name in raw:
            v = raw[name]
            if v is None or isinstance(v, bool) or not math.isfinite(float(v)):
                raise ValueError(f"'{name}' must be a number")
            setattr(cfg, name, float(v))
    cfg.thinnest_awg = int(cfg.thinnest_awg)
    if "round_trip" in raw:
        cfg.round_trip = bool(raw["round_trip"])
    return cfg


def run(rows_json: str, config_json: str, catalog_text: str, title: str = "harness") -> str:
    """Size every part. Always returns JSON: {"ok": false, "kind", "problems"} on bad input."""
    try:
        cfg = _config(json.loads(config_json))
    except (TypeError, ValueError, AttributeError) as e:
        return json.dumps({"ok": False, "kind": "config", "problems": [f"invalid settings: {e}"]})
    if cfg.problems():
        return json.dumps({"ok": False, "kind": "config", "problems": cfg.problems()})

    try:
        cat = parse_catalog(io.StringIO(catalog_text.lstrip("﻿")))
    except CatalogError as e:
        return json.dumps({"ok": False, "kind": "catalog", "problems": e.problems})
    try:
        parts = parse_bom(io.StringIO(rows_to_csv(rows_json)))
    except BomError as e:
        return json.dumps({"ok": False, "kind": "bom", "problems": e.problems})

    results = size_bom(parts, cfg, cat)
    return json.dumps({
        "ok": True,
        "results": [
            {
                "row": r.part.row, "part": r.part.part, "current_a": r.part.current_a,
                "length_mm": r.part.length_mm, "terminals": r.part.terminals,
                "awg": r.awg, "electrical_awg": r.electrical_awg, "limited_by": r.limited_by,
                "terminal_range": list(r.terminal_range) if r.terminal_range else None,
                "ampacity_a": r.ampacity_a, "drop_v": r.drop_v, "drop_pct": r.drop_pct,
                "notes": r.notes, "ok": r.ok,
            }
            for r in results
        ],
        "files": {"report_md": render_markdown(results, cfg, title), "results_csv": render_csv(results)},
    })
