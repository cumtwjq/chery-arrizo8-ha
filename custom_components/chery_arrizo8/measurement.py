"""Verified display units and numeric parsing for vehicle measurements."""

from __future__ import annotations

import math


UNITS = {
    "odometer": "km",
    "mileageSurplus": "km",
    "oilSurplus": "%",
    "averageFuel": "L/100km",
    "leftFrontTyrekPa": "kPa",
    "rightFrontTyrekPa": "kPa",
    "leftRearTyrekPa": "kPa",
    "rightRearTyrekPa": "kPa",
    "lAreaTemp": "°C",
    "rAreaTemp": "°C",
}


def numeric_value(value: object) -> int | float | None:
    """Return a finite number from the vehicle's numeric fields."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if number.is_integer():
        return int(number)
    return number
