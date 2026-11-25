"""Electrical calculations for choosing a wire gauge. No file I/O here."""

from __future__ import annotations

import math

from .tables import (
    ALPHA_CU,
    GAUGES_THIN_TO_THICK,
    INSULATION_RATING_C,
    REF_AMBIENT_C,
    WIRE_TABLE,
    WireSpec,
)


def wire_spec(awg: int) -> WireSpec:
    try:
        return WIRE_TABLE[awg]
    except KeyError:
        supported = ", ".join(str(g) for g in GAUGES_THIN_TO_THICK)
        raise ValueError(f"unsupported gauge AWG {awg} (supported: {supported})") from None


def ambient_factor(ambient_c: float) -> float:
    """Ampacity multiplier for ambient temperature.

    The heat a wire can shed scales with (T_insulation - T_ambient), and I^2*R
    heating scales with I^2, so allowable current scales with the square root.
    """
    if ambient_c >= INSULATION_RATING_C:
        return 0.0
    return math.sqrt((INSULATION_RATING_C - ambient_c) / (INSULATION_RATING_C - REF_AMBIENT_C))


def ampacity(awg: int, ambient_c: float = REF_AMBIENT_C) -> float:
    return wire_spec(awg).ampacity_a * ambient_factor(ambient_c)


def conductor_temp(current_a: float, ampacity_a: float, ambient_c: float) -> float:
    """Estimated conductor temperature: reaches the insulation rating at full ampacity."""
    if ampacity_a <= 0:
        return INSULATION_RATING_C
    rise = (INSULATION_RATING_C - ambient_c) * (current_a / ampacity_a) ** 2
    return min(ambient_c + rise, INSULATION_RATING_C)


def voltage_drop(awg: int, current_a: float, wire_length_m: float, ambient_c: float = REF_AMBIENT_C) -> float:
    """I * R, with resistance taken at the wire's estimated operating temperature."""
    temp = conductor_temp(current_a, ampacity(awg, ambient_c), ambient_c)
    ohms = wire_spec(awg).ohm_per_km_20c * wire_length_m / 1000.0 * (1 + ALPHA_CU * (temp - 20.0))
    return current_a * ohms


def thinnest_passing(test, thinnest_allowed_awg: int) -> int | None:
    """Thinnest gauge (no thinner than the allowed minimum) for which test(awg) is true."""
    for awg in GAUGES_THIN_TO_THICK:
        if awg <= thinnest_allowed_awg and test(awg):
            return awg
    return None


def electrical_minimum(
    current_a: float,
    wire_length_m: float,
    max_drop_v: float,
    ambient_c: float,
    thinnest_allowed_awg: int,
) -> tuple[int | None, str]:
    """Thinnest gauge that carries the current and keeps the drop in limit.

    Returns (awg, limited_by), where limited_by says which requirement set the
    size: "current", "voltage drop" or "minimum gauge". awg is None when no
    gauge in the table is big enough.
    """
    by_current = thinnest_passing(lambda g: ampacity(g, ambient_c) >= current_a, thinnest_allowed_awg)
    by_drop = thinnest_passing(
        lambda g: voltage_drop(g, current_a, wire_length_m, ambient_c) <= max_drop_v + 1e-12,
        thinnest_allowed_awg,
    )
    if by_current is None:
        return None, "current"
    if by_drop is None:
        return None, "voltage drop"

    # Both checks get easier as the wire gets thicker, so the thicker of the
    # two answers (smaller AWG number) satisfies both.
    awg = min(by_current, by_drop)
    if awg == thinnest_allowed_awg:
        return awg, "minimum gauge"
    return awg, "voltage drop" if by_drop < by_current else "current"
