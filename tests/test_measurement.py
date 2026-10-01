"""Vehicle measurements should remain usable as numeric HA sensor states."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "chery_arrizo8" / "measurement.py"
spec = importlib.util.spec_from_file_location("chery_measurement", MODULE)
assert spec is not None and spec.loader is not None
measurement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measurement)


class MeasurementTest(unittest.TestCase):
    def test_numeric_strings_and_values(self) -> None:
        self.assertEqual(measurement.numeric_value("82"), 82)
        self.assertEqual(measurement.numeric_value("7.2"), 7.2)
        self.assertEqual(measurement.numeric_value(235), 235)

    def test_invalid_values_do_not_become_measurements(self) -> None:
        for value in ("", "unknown", "nan", "inf", True, None, {}, 10**400):
            with self.subTest(value=value):
                self.assertIsNone(measurement.numeric_value(value))

    def test_user_confirmed_fuel_unit(self) -> None:
        self.assertEqual(measurement.UNITS["oilSurplus"], "%")
        self.assertEqual(measurement.UNITS["odometer"], "km")
        self.assertEqual(measurement.UNITS["mileageSurplus"], "km")
