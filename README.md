# wire-harness-calculator

Picks the right wire gauge for each part on a harness BOM.

For every part, harnesscalc finds the thinnest wire that:
1. **carries the part's current** (ampacity, corrected for ambient temperature),
2. **keeps the voltage drop** within your limit over the run length, and
3. **fits every terminal** listed for that part, based on the terminal catalog.

If the terminals force a thicker wire than the electrical calculation needs, the
report says so. If no gauge satisfies all three, the part is flagged with advice,
for example "needs AWG 12 or thicker, but EX-SKT-16 only takes AWG 16-20; choose a
terminal rated for AWG 12".

```
$ harnesscalc examples/front_lighting.csv
12 V supply · max drop 5% · ambient 30 C · thinnest AWG 22 · length round trip (return wire)

PART                 LOAD A  LENGTH mm  TERMINALS   AWG  SET BY         DROP %  STATUS
Headlamp left        4.6     3000       EX-SKT-16   16   voltage drop   3.20    OK
Horn                 8       2500       EX-RING-14  16   voltage drop   4.78    OK
Fuel pump            10      4000       EX-SKT-16   -    voltage drop   -       CHECK
Cooling fan          18      1500       EX-RING-10  12   terminal       2.61    OK
...
```

## Web GUI

The browser interface lets you edit the parts list, change the design limits and
load your own terminal catalog. Results update as you type. It runs this same
Python package in the browser through [Pyodide](https://pyodide.org), so there's
no backend to host.

From the project folder, run:

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000/web/>. You have to serve the folder like this:
opening `web/index.html` directly as a file won't work.

**GitHub Pages:** in the repository's *Settings → Pages*, set *Source* to
**GitHub Actions**. The `Deploy web GUI` workflow then publishes the GUI on every
push to `main`.

## Command line

```bash
pip install -e ".[dev]"
harnesscalc my_bom.csv                          # print the gauge table
harnesscalc my_bom.csv -t my_terminals.csv      # use your own terminal catalog
harnesscalc my_bom.csv -o out/                  # also write Markdown + CSV reports
```

| Option | Default | Meaning |
|---|---|---|
| `-t`, `--terminals` | built-in example | Terminal catalog CSV |
| `-o`, `--out` | none | Folder for `<bom>_gauges.md` and `<bom>_gauges.csv` |
| `--supply-voltage` | 12 | System voltage (V) |
| `--max-drop-pct` | 5 | Allowed voltage drop (%) |
| `--ambient` | 30 | Ambient temperature (°C) |
| `--thinnest-awg` | 22 | Thinnest gauge allowed, for mechanical strength |
| `--chassis-return` | off | Parts are grounded to chassis nearby: count the length one way instead of round trip |

Exit codes: `0` means every part was sized, `1` means one or more parts need
attention, and `2` means the input or settings are invalid.

## Input files

**Parts BOM** has one row per part that needs a wire:

| Column | Required | Meaning |
|---|---|---|
| `part` | yes | Part name |
| `current_a` | yes | Continuous current the part draws (A) |
| `length_mm` | yes | One-way wire run from the power source to the part |
| `terminals` | no | Terminal/connector part numbers on the wire, separated by `;` |

**Terminal catalog** has one row per terminal part number:

| Column | Required | Meaning |
|---|---|---|
| `part_number` | yes | Matched against the BOM's `terminals` column (case-insensitive) |
| `wire_range_awg` | yes | Wire sizes it accepts, such as `14-16`, or `16` for a single size |
| `description` | no | Shown in the GUI |

The built-in catalog ([harnesscalc/data/terminals.csv](harnesscalc/data/terminals.csv))
uses **made-up example part numbers**. Replace it with real terminals and the wire
ranges from their datasheets.

## How the gauge is chosen

| Check | Method |
|---|---|
| Ampacity | Free-air rating × √((125 °C − ambient) / (125 °C − 30 °C)) |
| Voltage drop | I × R, where R = R<sub>20</sub> × length × (1 + 0.00393 × (T − 20)), at the wire's estimated operating temperature. Length is doubled for a return wire |
| Terminal fit | The gauge must be inside every listed terminal's range |
| Result | The thinnest gauge passing all checks, never thinner than the mechanical minimum |

The "set by" column shows which requirement decided the size: current, voltage
drop, minimum gauge, or terminal.

## Project layout

```
harnesscalc/
  tables.py      wire data (resistance, ampacity)
  calcs.py       ampacity, voltage drop, electrical minimum gauge
  terminals.py   terminal catalog parsing and fit checks
  bom.py         parts BOM parsing and validation
  sizing.py      combines the electrical and terminal requirements per part
  report.py      terminal table, Markdown and CSV output
  cli.py         command-line interface
  webapi.py      JSON entry points used by the web GUI
  data/terminals.csv   example terminal catalog
web/             browser GUI (runs the package via Pyodide)
tests/           pytest suite
examples/        sample parts BOM
```

## Assumptions and limits

- Wire data are typical SAE J1128 TXL values (125 °C insulation). They are not
  certified data, so check them against your wire's datasheet.
- Each part gets its own wire. Shared feeds and grounds through splices aren't
  modeled; size those by hand from the combined current.
- Bundle derating is not applied. Wires in tightly packed bundles run hotter, so
  for heavily loaded bundles choose one size up or verify against your standard.
- Calculations are DC steady state only. Motor inrush current is not considered.
