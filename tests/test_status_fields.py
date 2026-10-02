"""Useful vehicle states are visible without leaking identifiers or GPS."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "chery_arrizo8" / "status_fields.py"
spec = importlib.util.spec_from_file_location("chery_status_fields", MODULE)
assert spec is not None and spec.loader is not None
status_fields = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status_fields)


class StatusFieldsTest(unittest.TestCase):
    def test_device_page_order(self) -> None:
        self.assertEqual(set(status_fields.DISPLAY_ORDER), status_fields.ACTIVE_FIELDS)
        self.assertEqual(len(set(status_fields.DISPLAY_ORDER.values())), len(status_fields.DISPLAY_ORDER))
        self.assertEqual(status_fields.ordered_label("time", "车辆上报时间"), "01 车辆上报时间")
        self.assertEqual(status_fields.ordered_label("odometer", "总里程"), "04 总里程")
        self.assertEqual(status_fields.ordered_label("averageFuel", "平均油耗"), "05 平均油耗")
        self.assertEqual(status_fields.ordered_label("mileageSurplus", "剩余续航"), "06 剩余续航")
        self.assertEqual(status_fields.ordered_label("rAreaTemp", "右侧空调温度"), "98 右侧空调温度")
        self.assertEqual(status_fields.ordered_label("lAreaTemp", "左侧空调温度"), "99 左侧空调温度")

    def test_active_fields_are_named_and_include_requested_status(self) -> None:
        self.assertTrue(status_fields.ACTIVE_FIELDS <= status_fields.LABELS.keys())
        for key in ("oilSurplus", "doorLock", "frontLeftWindowState", "sunroofState", "airState"):
            self.assertIn(key, status_fields.ACTIVE_FIELDS)
        self.assertNotIn("mSeatHeatingState2", status_fields.ACTIVE_FIELDS)

    def test_binary_open_close_display(self) -> None:
        self.assertEqual(status_fields.display_status_value("frontLeftDoor", "0"), "关闭")
        for key in status_fields.OPEN_CLOSE_FIELDS:
            self.assertEqual(status_fields.display_status_value(key, 1), "开启")
        self.assertEqual(status_fields.display_status_value("frontLeftWindowState", 2), "关闭")
        for key in ("frontLeftWindowState", "frontRightWindowState", "backLeftWindowState", "backRightWindowState"):
            self.assertEqual(status_fields.display_status_value(key, 1), "通风")
            self.assertEqual(status_fields.display_status_value(key, 3), "完全开启")
        self.assertEqual(status_fields.display_status_value("sunroofState", "1"), "关闭")
        self.assertEqual(status_fields.display_status_value("sunroofState", 2), "开启")
        self.assertEqual(status_fields.display_status_value("sunroofState", 9), "翘起")
        self.assertEqual(status_fields.display_status_value("sunroofState", 12), "翘起")
        self.assertEqual(status_fields.display_status_value("airState", "1"), "关闭")
        self.assertEqual(status_fields.display_status_value("airState", 0), "开启")
        self.assertEqual(status_fields.display_status_value("doorLock", 0), "已锁")
        self.assertEqual(status_fields.display_status_value("doorLock", 1), "已解锁")
        self.assertEqual(status_fields.display_status_value("engineState", 0), "熄火")
        self.assertEqual(status_fields.display_status_value("engineState", 1), "运行")
        self.assertEqual(status_fields.display_status_value("sunroofState", 7), "开启")
        self.assertEqual(status_fields.display_status_value("frontLeftWindowState", 0), "开启")
        self.assertEqual(status_fields.display_status_value("frontLeftWindowState", "2.0"), "关闭")
        self.assertEqual(status_fields.display_status_value("airState", 2), "开启")
        self.assertEqual(status_fields.display_status_value("doorLock", 2), "已解锁")
        self.assertEqual(status_fields.display_status_value("frontLeftDoor", 2), "开启")
        self.assertEqual(status_fields.display_status_value("sunroofState", None), None)
        self.assertEqual(status_fields.display_status_value("sunroofState", "bad"), "未识别状态（代码 bad）")
        self.assertEqual(status_fields.display_status_value("oilSurplus", 0), 0)

    def test_diagnostics_excludes_private_values(self) -> None:
        shape = status_fields.diagnostic_status_shape({
            "doorLock": "1", "oilSurplus": 1, "lat": 31.1,
            "vin": "EXAMPLE12345678901", "newVendorCode": "private",
        })
        self.assertEqual(shape["doorLock"], {"type": "str", "binary_code": "1"})
        self.assertEqual(shape["oilSurplus"], {"type": "int"})
        self.assertEqual(shape["newVendorCode"], {"type": "str"})
        self.assertNotIn("vin", shape)
        self.assertNotIn("lat", shape)

    def test_windows_roof_and_new_scalar_field(self) -> None:
        fields = dict(status_fields.safe_status_fields({
            "frontLeftWindowState": "0",
            "sunroofState": 1,
            "newVendorCode": "2",
            "vin": "EXAMPLE12345678901",
            "lat": 31.12,
            "lon": 121.43,
            "deviceId": "private",
            "ownerName": "private",
            "nested": {"value": 1},
        }))
        self.assertEqual(fields["frontLeftWindowState"], "左前车窗")
        self.assertEqual(fields["sunroofState"], "天窗状态")
        self.assertIn("newVendorCode", fields)
        for key in ("vin", "lat", "lon", "deviceId", "ownerName", "nested"):
            self.assertNotIn(key, fields)
