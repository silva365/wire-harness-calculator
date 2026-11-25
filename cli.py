"""Command-line entry point: harnesscalc BOM.csv [options]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bom import BomError, read_bom
from .report import render_csv, render_markdown, render_text
from .sizing import Config, size_bom
from .terminals import DEFAULT_CATALOG, CatalogError, load_catalog


def build_parser() -> argparse.ArgumentParser:
    d = Config()
    p = argparse.ArgumentParser(
        prog="harnesscalc",
        description="Pick the wire gauge for each part on a BOM from its current, run length and terminals.",
    )
    p.add_argument("bom", type=Path, help="parts BOM CSV (part, current_a, length_mm, terminals)")
    p.add_argument("-t", "--terminals", type=Path, default=DEFAULT_CATALOG,
                   help="terminal catalog CSV (default: built-in example catalog)")
    p.add_argument("-o", "--out", type=Path, help="also write <bom>_gauges.md and <bom>_gauges.csv here")
    p.add_argument("--supply-voltage", type=float, default=d.supply_voltage, help="system voltage, V (default 12)")
    p.add_argument("--max-drop-pct", type=float, default=d.max_drop_pct, help="allowed voltage drop, %% (default 5)")
    p.add_argument("--ambient", type=float, default=d.ambient_c, help="ambient temperature, C (default 30)")
    p.add_argument("--thinnest-awg", type=int, default=d.thinnest_awg,
                   help="thinnest gauge allowed for mechanical strength (default 22)")
    p.add_argument("--chassis-return", action="store_true",
                   help="parts are grounded to chassis nearby: count the length one way, not round trip")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config(args.supply_voltage, args.max_drop_pct, args.ambient, args.thinnest_awg, not args.chassis_return)
    if cfg.problems():
        for prob in cfg.problems():
            print(f"invalid setting: {prob}", file=sys.stderr)
        return 2

    try:
        catalog = load_catalog(args.terminals)
        parts = read_bom(args.bom)
    except (BomError, CatalogError) as e:
        print(f"{len(e.problems)} problem(s) in the input:", file=sys.stderr)
        for prob in e.problems:
            print(f"  - {prob}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"cannot read file: {e}", file=sys.stderr)
        return 2

    results = size_bom(parts, cfg, catalog)
    print(render_text(results, cfg))

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        stem = args.bom.stem
        (args.out / f"{stem}_gauges.md").write_text(render_markdown(results, cfg, stem), encoding="utf-8")
        (args.out / f"{stem}_gauges.csv").write_text(render_csv(results), encoding="utf-8")
        print(f"\nWrote {args.out / (stem + '_gauges.md')} and {args.out / (stem + '_gauges.csv')}")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
