"""The temporary schema collector must not persist vehicle values."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / "research" / "status_keys.py"
spec = importlib.util.spec_from_file_location("status_keys", MODULE)
assert spec is not None and spec.loader is not None
status_keys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status_keys)


class StatusShapeTest(unittest.TestCase):
    def test_saves_names_and_types_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "shape.json"
            payload = {"data": json.dumps({"frontWindow": "1.0", "vin": "EXAMPLE12345678901", "lat": 31.123})}
            flow = SimpleNamespace(
                request=SimpleNamespace(
                    pretty_url="https://cloudrivechery.mychery.com/cheryAppData/vehicleRealtimeData/example"
                ),
                response=SimpleNamespace(status_code=200, raw_content=json.dumps(payload).encode()),
            )
            with patch.object(status_keys, "DESTINATION", destination):
                status_keys._saved = False
                status_keys.response(flow)
            shape = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(shape["frontWindow"], "numeric_text")
            self.assertEqual(shape["vin"], "text")
            self.assertEqual(shape["lat"], "number")
            self.assertNotIn("EXAMPLE12345678901", destination.read_text(encoding="utf-8"))
