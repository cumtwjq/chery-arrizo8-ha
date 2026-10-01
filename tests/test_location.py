"""Coordinate parsing cases that affect map visibility and placement."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
import unittest


MODULE_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "chery_arrizo8"
package = types.ModuleType("chery_arrizo8")
package.__path__ = [str(MODULE_DIR)]
sys.modules[package.__name__] = package
location = importlib.import_module("chery_arrizo8.location")


class PositionTest(unittest.TestCase):
    def test_decimal_string(self) -> None:
        self.assertEqual(location.parse_position({"lat": "31.25", "lon": "121.5"}), (31.25, 121.5))

    def test_unusable_fixes(self) -> None:
        for fields in (
            {},
            {"lat": "0", "lon": "0"},
            {"lat": "nan", "lon": "121"},
            {"lat": "91", "lon": "121"},
            {"lat": "31", "lon": "181"},
            {"lat": "", "lon": "121"},
        ):
            with self.subTest(fields=fields):
                self.assertIsNone(location.parse_position(fields))

    def test_gcj02_conversion_round_trip(self) -> None:
        original = (39.915, 116.404)
        gcj = location._wgs84_to_gcj02(*original)
        self.assertAlmostEqual(gcj[0], 39.916404, places=5)
        self.assertAlmostEqual(gcj[1], 116.410244, places=5)
        restored = location.map_position({"lat": str(gcj[0]), "lon": str(gcj[1])}, "gcj02")
        self.assertIsNotNone(restored)
        self.assertAlmostEqual(restored[0], original[0], places=6)
        self.assertAlmostEqual(restored[1], original[1], places=6)

    def test_bd09_conversion(self) -> None:
        gcj = (39.916404, 116.410244)
        x, y = gcj[1], gcj[0]
        radius = (x * x + y * y) ** 0.5 + 0.00002 * location.math.sin(y * location.X_PI)
        angle = location.math.atan2(y, x) + 0.000003 * location.math.cos(x * location.X_PI)
        bd_lat = radius * location.math.sin(angle) + 0.006
        bd_lon = radius * location.math.cos(angle) + 0.0065
        converted = location._bd09_to_gcj02(bd_lat, bd_lon)
        self.assertAlmostEqual(converted[0], gcj[0], places=5)
        self.assertAlmostEqual(converted[1], gcj[1], places=5)

    def test_outside_china_is_unchanged(self) -> None:
        original = {"lat": "48.85", "lon": "2.35"}
        self.assertEqual(location.map_position(original, "gcj02"), (48.85, 2.35))


if __name__ == "__main__":
    unittest.main()
