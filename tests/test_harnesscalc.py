import io
import json
import math
from pathlib import Path

import pytest

from harnesscalc import calcs, webapi
from harnesscalc.bom import BomError, parse_bom, read_bom, split_terminals
from harnesscalc.cli import main
from harnesscalc.sizing import Config, size_bom, size_part
from harnesscalc.terminals import DEFAULT_CATALOG, CatalogError, load_catalog, parse_catalog, parse_range

EXAMPLE = Path(__file__).parent.parent / "examples" / "front_lighting.csv"


def bom(text):
    return parse_bom(io.StringIO(text))


def cat(text):
    return parse_catalog(io.StringIO(text))


CATALOG = cat(
    "part_number,wire_range_awg\n"
    "SKT-16,16-20\n"
    "SKT-12,12-14\n"
    "RING-14,14-16\n"
    "RING-10,10-12\n"
)


def one(text_row, cfg=None, catalog=CATALOG):
    return size_part(bom("part,current_a,length_mm,terminals\n" + text_row)[0], cfg or Config(), catalog)


# --- calculations -----------------------------------------------------------

def test_ambient_factor():
    assert calcs.ambient_factor(30) == pytest.approx(1.0)
    assert calcs.ambient_factor(85) == pytest.approx(math.sqrt(40 / 95))
    assert calcs.ambient_factor(125) == 0.0


def test_voltage_drop_at_no_load_temperature():
    # Tiny current: conductor stays at 30 C ambient.
    r = 20.95 / 1000 * (1 + 0.00393 * 10)
    assert calcs.voltage_drop(18, 0.001, 1.0) == pytest.approx(0.001 * r, rel=1e-4)


def test_electrical_minimum_reports_what_limits_it():
    # Short, heavy load: current decides.
    assert calcs.electrical_minimum(25, 0.5, 0.6, 30, 22) == (14, "current")
    # Long, light load: voltage drop decides.
    assert calcs.electrical_minimum(4.6, 6.0, 0.6, 30, 22) == (16, "voltage drop")
    # Signal: mechanical minimum decides.
    assert calcs.electrical_minimum(0.01, 4.0, 0.6, 30, 22) == (22, "minimum gauge")
    # Nothing in the table is big enough.
    assert calcs.electrical_minimum(500, 1.0, 0.6, 30, 22) == (None, "current")


# --- terminal catalog ---------------------------------------------------------

@pytest.mark.parametrize("text, expected", [("14-16", (14, 16)), ("16 - 14", (14, 16)), ("16", (16, 16)),
                                            ("14 to 16", (14, 16))])
def test_parse_range(text, expected):
    assert parse_range(text) == expected


@pytest.mark.parametrize("bad", ["", "abc", "14-16-18", "14,16", "100"])
def test_parse_range_rejects(bad):
    with pytest.raises(ValueError):
        parse_range(bad)


def test_catalog_lookup_is_case_insensitive():
    r = one("Lamp,1,500, skt-16 ")
    assert r.ok and r.terminal_range == (16, 20)


def test_catalog_reports_all_problems():
    with pytest.raises(CatalogError) as e:
        cat("part_number,wire_range_awg\nA,14-16\nA,16\n,18\nB,big\n")
    assert len(e.value.problems) == 3


def test_default_catalog_loads():
    assert "EX-SKT-16" in load_catalog(DEFAULT_CATALOG)


# --- BOM parsing --------------------------------------------------------------

def test_split_terminals():
    assert split_terminals(" A ; B|C;; ") == ["A", "B", "C"]


def test_reads_example():
    parts = read_bom(EXAMPLE)
    assert parts[0].part == "Headlamp left" and parts[0].terminals == ["EX-SKT-16"]
    assert parts[-1].terminals == []


def test_bom_reports_all_problems():
    with pytest.raises(BomError) as e:
        bom("part,current_a,length_mm\n,1,100\nB,abc,100\nC,1,-5\nD,nan,100\n")
    assert len(e.value.problems) == 4


def test_bom_missing_column():
    with pytest.raises(BomError, match="length_mm"):
        bom("part,current_a\nA,1\n")


# --- sizing -------------------------------------------------------------------

def test_terminal_forces_thicker_wire():
    r = one("Fan,18,1500,RING-10")
    assert (r.electrical_awg, r.awg, r.limited_by, r.ok) == (14, 12, "terminal", True)


def test_terminal_too_small_fails_with_advice():
    r = one("Pump,10,4000,SKT-16")
    assert r.awg is None and not r.ok
    assert "choose a terminal rated for AWG 12" in r.notes[0]


def test_both_ends_must_fit():
    r = one("Horn,8,1000,SKT-16;RING-14")    # common range is 16 only
    assert r.ok and r.terminal_range == (16, 16) and r.awg == 16


def test_ends_with_no_common_size_fail():
    r = one("X,1,500,SKT-16;RING-10")
    assert not r.ok and "share no wire size" in r.notes[0]


def test_unknown_terminal_fails_but_still_sizes():
    r = one("X,4.6,3000,NOPE-1")
    assert not r.ok and r.awg == 16 and "NOPE-1" in r.notes[0]


def test_no_terminals_uses_electrical_size():
    r = one("Dome,0.8,2800,")
    assert r.ok and r.awg == r.electrical_awg == 22


def test_chassis_return_halves_the_length():
    rt = one("Pump,10,4000,", Config(round_trip=True))
    ch = one("Pump,10,4000,", Config(round_trip=False))
    assert ch.awg > rt.awg     # one-way run needs a thinner wire


def test_drop_within_limit_for_every_sized_part():
    cfg = Config()
    for r in size_bom(read_bom(EXAMPLE), cfg, load_catalog()):
        if r.awg is not None:
            assert r.drop_pct <= cfg.max_drop_pct
            assert r.ampacity_a >= r.part.current_a


def test_example_results():
    rs = {r.part.part: r for r in size_bom(read_bom(EXAMPLE), Config(), load_catalog())}
    assert rs["Headlamp left"].awg == 16
    assert rs["Cooling fan"].awg == 12 and rs["Cooling fan"].limited_by == "terminal"
    assert not rs["Fuel pump"].ok
    assert [p for p, r in rs.items() if not r.ok] == ["Fuel pump"]


# --- web API ------------------------------------------------------------------

def example_rows():
    return json.loads(webapi.csv_to_rows(EXAMPLE.read_text()))["rows"]


def test_csv_round_trip():
    rows = example_rows()
    again = json.loads(webapi.csv_to_rows(webapi.rows_to_csv(json.dumps(rows))))["rows"]
    assert again == rows and rows[0]["terminals"] == "EX-SKT-16"


def test_web_run_matches_cli():
    out = json.loads(webapi.run(json.dumps(example_rows()), "{}", DEFAULT_CATALOG.read_text()))
    assert out["ok"]
    assert [r["part"] for r in out["results"] if not r["ok"]] == ["Fuel pump"]
    assert out["files"]["report_md"].startswith("# Wire gauges")


@pytest.mark.parametrize("cfg", [{"supply_voltage": None}, {"supply_voltage": "x"}, {"ambient_c": 200},
                                 {"thinnest_awg": 17}])
def test_web_run_rejects_bad_settings(cfg):
    out = json.loads(webapi.run(json.dumps(example_rows()), json.dumps(cfg), DEFAULT_CATALOG.read_text()))
    assert out["ok"] is False and out["kind"] == "config"


def test_web_run_reports_catalog_and_bom_problems():
    bad_cat = json.loads(webapi.run(json.dumps(example_rows()), "{}", "part_number\nA\n"))
    assert bad_cat["kind"] == "catalog"
    rows = example_rows()
    rows[1]["current_a"] = "lots"
    bad_bom = json.loads(webapi.run(json.dumps(rows), "{}", DEFAULT_CATALOG.read_text()))
    assert bad_bom == {"ok": False, "kind": "bom", "problems": ["row 3: 'current_a' must be a number, got 'lots'"]}


def test_web_catalog_listing():
    out = json.loads(webapi.catalog(DEFAULT_CATALOG.read_text()))
    assert out["ok"] and {"part_number": "EX-SKT-16", "description": "Example sealed socket - standard",
                          "range": "16-20"} in out["terminals"]


# --- CLI ----------------------------------------------------------------------

def test_cli(tmp_path, capsys):
    assert main([str(EXAMPLE), "-o", str(tmp_path)]) == 1          # fuel pump needs attention
    out = capsys.readouterr().out
    assert "Cooling fan" in out and "CHECK" in out
    assert (tmp_path / "front_lighting_gauges.md").exists()
    assert (tmp_path / "front_lighting_gauges.csv").exists()


def test_cli_all_ok_exit_code(tmp_path):
    p = tmp_path / "ok.csv"
    p.write_text("part,current_a,length_mm,terminals\nLamp,2,1000,EX-SKT-16\n")
    assert main([str(p)]) == 0


def test_cli_bad_input_exit_code(tmp_path, capsys):
    p = tmp_path / "bad.csv"
    p.write_text("part,current_a\nA,1\n")
    assert main([str(p)]) == 2
    assert "missing required column" in capsys.readouterr().err
