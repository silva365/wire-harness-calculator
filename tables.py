"""Wire reference data.

Typical figures for stranded copper automotive wire (SAE J1128 TXL style,
125 C insulation). They are sensible defaults, not certified data: check them
against the datasheet of the wire you actually buy.
"""

from typing import NamedTuple


class WireSpec(NamedTuple):
    area_mm2: float          # conductor cross-section
    ohm_per_km_20c: float    # DC resistance at 20 C
    ampacity_a: float        # single wire, free air, 30 C ambient, 125 C insulation


WIRE_TABLE: dict[int, WireSpec] = {
    26: WireSpec(0.129, 133.9, 4),
    24: WireSpec(0.205, 84.2, 6),
    22: WireSpec(0.326, 52.96, 9),
    20: WireSpec(0.518, 33.31, 12),
    18: WireSpec(0.823, 20.95, 17),
    16: WireSpec(1.31, 13.17, 22),
    14: WireSpec(2.08, 8.286, 30),
    12: WireSpec(3.31, 5.211, 40),
    10: WireSpec(5.26, 3.277, 55),
    8: WireSpec(8.37, 2.061, 75),
    6: WireSpec(13.3, 1.296, 100),
    4: WireSpec(21.2, 0.8152, 135),
    2: WireSpec(33.6, 0.5127, 180),
}

# Thinnest (highest AWG number) to thickest.
GAUGES_THIN_TO_THICK = sorted(WIRE_TABLE, reverse=True)

ALPHA_CU = 0.00393           # copper resistance temperature coefficient, per C
REF_AMBIENT_C = 30.0         # ambient the ampacity column is referenced to
INSULATION_RATING_C = 125.0  # TXL insulation rating
