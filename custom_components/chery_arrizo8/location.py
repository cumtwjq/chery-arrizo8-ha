"""Validate the coordinates reported by the vehicle status endpoint."""

from __future__ import annotations

import math
from typing import Any

from .const import COORDINATE_SYSTEM_BD09, COORDINATE_SYSTEM_GCJ02


PI = math.pi
X_PI = PI * 3000.0 / 180.0
EARTH_SEMI_MAJOR = 6378245.0
EARTH_ECCENTRICITY_SQUARED = 0.006693421622965943


def parse_position(status: dict[str, Any]) -> tuple[float, float] | None:
    """Return decimal-degree coordinates, or None for missing/invalid fixes."""
    try:
        latitude = float(status["lat"])
        longitude = float(status["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    if latitude == 0 or longitude == 0:
        return None
    return latitude, longitude


def _inside_china(latitude: float, longitude: float) -> bool:
    return 3.86 <= latitude <= 53.55 and 73.66 <= longitude <= 135.05


def _latitude_offset(x: float, y: float) -> float:
    result = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
    result += 0.2 * math.sqrt(abs(x))
    result += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    result += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    result += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return result


def _longitude_offset(x: float, y: float) -> float:
    result = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y
    result += 0.1 * math.sqrt(abs(x))
    result += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    result += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    result += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return result


def _wgs84_to_gcj02(latitude: float, longitude: float) -> tuple[float, float]:
    """Forward transform, used to iteratively invert a GCJ-02 point."""
    if not _inside_china(latitude, longitude):
        return latitude, longitude
    x, y = longitude - 105.0, latitude - 35.0
    delta_latitude = _latitude_offset(x, y)
    delta_longitude = _longitude_offset(x, y)
    radian_latitude = latitude / 180.0 * PI
    magic = 1.0 - EARTH_ECCENTRICITY_SQUARED * math.sin(radian_latitude) ** 2
    sqrt_magic = math.sqrt(magic)
    delta_latitude = delta_latitude * 180.0 / (
        (EARTH_SEMI_MAJOR * (1.0 - EARTH_ECCENTRICITY_SQUARED)) / (magic * sqrt_magic) * PI
    )
    delta_longitude = delta_longitude * 180.0 / (
        EARTH_SEMI_MAJOR / sqrt_magic * math.cos(radian_latitude) * PI
    )
    return latitude + delta_latitude, longitude + delta_longitude


def _gcj02_to_wgs84(latitude: float, longitude: float) -> tuple[float, float]:
    if not _inside_china(latitude, longitude):
        return latitude, longitude
    guess_latitude, guess_longitude = latitude, longitude
    for _ in range(6):
        forward_latitude, forward_longitude = _wgs84_to_gcj02(guess_latitude, guess_longitude)
        guess_latitude -= forward_latitude - latitude
        guess_longitude -= forward_longitude - longitude
    return guess_latitude, guess_longitude


def _bd09_to_gcj02(latitude: float, longitude: float) -> tuple[float, float]:
    x, y = longitude - 0.0065, latitude - 0.006
    radius = math.hypot(x, y) - 0.00002 * math.sin(y * X_PI)
    angle = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    return radius * math.sin(angle), radius * math.cos(angle)


def map_position(status: dict[str, Any], coordinate_system: str) -> tuple[float, float] | None:
    """Convert the selected source system to WGS-84 for Home Assistant maps."""
    position = parse_position(status)
    if position is None:
        return None
    latitude, longitude = position
    if not _inside_china(latitude, longitude):
        return position
    if coordinate_system == COORDINATE_SYSTEM_BD09:
        latitude, longitude = _bd09_to_gcj02(latitude, longitude)
        return _gcj02_to_wgs84(latitude, longitude)
    if coordinate_system == COORDINATE_SYSTEM_GCJ02:
        return _gcj02_to_wgs84(latitude, longitude)
    return position
