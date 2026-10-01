"""Choose safe vehicle-status fields and their Home Assistant names."""

from __future__ import annotations

import re
from typing import Any


LABELS = {
    "odometer": "总里程",
    "mileageSurplus": "剩余续航",
    "oilSurplus": "剩余油量",
    "averageFuel": "平均油耗",
    "online": "车辆在线状态",
    "engineState": "发动机状态",
    "doorLock": "车锁状态",
    "frontLeftDoor": "左前门",
    "frontRightDoor": "右前门",
    "backLeftDoor": "左后门",
    "backRightDoor": "右后门",
    "trunkDoor": "后备厢门",
    "hood": "机盖",
    "leftFrontTyrekPa": "左前胎压",
    "rightFrontTyrekPa": "右前胎压",
    "leftRearTyrekPa": "左后胎压",
    "rightRearTyrekPa": "右后胎压",
    "frontLeftWindowState": "左前车窗",
    "frontRightWindowState": "右前车窗",
    "backLeftWindowState": "左后车窗",
    "backRightWindowState": "右后车窗",
    "flWindowState": "左前车窗",
    "frWindowState": "右前车窗",
    "blWindowState": "左后车窗",
    "brWindowState": "右后车窗",
    "sunroofState": "天窗状态",
    "sunroofOperateState": "天窗操作状态",
    "sunRoofAllOpen": "天窗全开状态",
    "sunRoofRaise": "天窗翘起状态",
    "rFrontTyreTemp": "右前胎温",
    "lFrontTyreTemp": "左前胎温",
    "lRearTyreTemp": "左后胎温",
    "rRearTyreTemp": "右后胎温",
    "lFrontTyreCall": "左前轮胎报警代码",
    "rFrontTyreCall": "右前轮胎报警代码",
    "lRearTyreCall": "左后轮胎报警代码",
    "rRearTyreCall": "右后轮胎报警代码",
    "pSeatHeatingState": "副驾座椅加热代码",
    "dSeatHeatingState": "主驾座椅加热代码",
    "pSeatVentilateState": "副驾座椅通风代码",
    "dSeatVentilateState": "主驾座椅通风代码",
    "mSeatHeatingState2": "M 座椅加热代码 2",
    "lSeatHeatingState2": "左侧座椅加热代码 2",
    "rSeatHeatingState2": "右侧座椅加热代码 2",
    "mSeatVentilateState2": "M 座椅通风代码 2",
    "lSeatVentilateState2": "左侧座椅通风代码 2",
    "rSeatVentilateState2": "右侧座椅通风代码 2",
    "fWinHeatingState": "前挡风玻璃加热代码",
    "lAreaTemp": "左侧空调温度",
    "rAreaTemp": "右侧空调温度",
    "airPur": "空气净化代码",
    "airState": "空调状态代码",
    "oilCall": "燃油报警代码",
    "waterTempCall": "水温报警代码",
    "speedCar": "车速",
    "systemDatetime": "系统时间",
    "trunkLock": "后备厢锁代码",
    "time": "车辆上报时间",
}

# Keep the device page focused on fields useful for day-to-day vehicle checks.
# Less understood vendor fields remain visible in the value-free diagnostics.
ACTIVE_FIELDS = frozenset({
    "odometer", "mileageSurplus", "oilSurplus", "averageFuel", "time",
    "lAreaTemp", "rAreaTemp",
    "leftFrontTyrekPa", "rightFrontTyrekPa", "leftRearTyrekPa",
    "rightRearTyrekPa", "frontLeftDoor", "frontRightDoor", "backLeftDoor",
    "backRightDoor", "trunkDoor", "hood", "doorLock",
    "frontLeftWindowState", "frontRightWindowState", "backLeftWindowState",
    "backRightWindowState", "sunroofState", "airState", "engineState",
})

# HA's device page sorts sensors by their displayed names. Keep these
# prefixes stable so existing unique IDs and automations are unaffected.
DISPLAY_ORDER = {
    "time": 1,
    "odometer": 4,
    "averageFuel": 5,
    "mileageSurplus": 6,
    "oilSurplus": 7,
    "doorLock": 8,
    "frontLeftDoor": 10,
    "frontRightDoor": 11,
    "backLeftDoor": 12,
    "backRightDoor": 13,
    "trunkDoor": 14,
    "hood": 15,
    "frontLeftWindowState": 16,
    "frontRightWindowState": 17,
    "backLeftWindowState": 18,
    "backRightWindowState": 19,
    "sunroofState": 20,
    "engineState": 21,
    "airState": 22,
    "leftFrontTyrekPa": 23,
    "rightFrontTyrekPa": 24,
    "leftRearTyrekPa": 25,
    "rightRearTyrekPa": 26,
    "rAreaTemp": 98,
    "lAreaTemp": 99,
}


def ordered_label(key: str, label: str) -> str:
    """Provide a stable visible order on HA's alphabetically sorted device page."""
    number = DISPLAY_ORDER.get(key)
    return f"{number:02d} {label}" if number is not None else label

# The captured snapshot confirmed 0 for closed doors, trunk and hood.
# The user's requested 1=open convention is limited to these fields.
OPEN_CLOSE_FIELDS = frozenset({
    "frontLeftDoor", "frontRightDoor", "backLeftDoor", "backRightDoor",
    "trunkDoor", "hood",
})

OBSERVED_STATE_CODES: dict[str, dict[str, str]] = {
    "frontLeftWindowState": {"2": "关闭"},
    "frontRightWindowState": {"2": "关闭"},
    "backLeftWindowState": {"2": "关闭"},
    "backRightWindowState": {"2": "关闭"},
    "sunroofState": {"1": "关闭"},
    "airState": {"1": "关闭"},
    "doorLock": {"0": "已锁"},
    "engineState": {"0": "熄火"},
}


def display_status_value(key: str, value: Any) -> Any:
    """Translate observed codes and the requested door open/close convention."""
    if key in OBSERVED_STATE_CODES and isinstance(value, (str, int, float)) and not isinstance(value, bool):
        code = str(value)
        return OBSERVED_STATE_CODES[key].get(code, f"未识别状态（代码 {code}）")
    if key in OPEN_CLOSE_FIELDS and not isinstance(value, bool):
        if value == 0 or value == "0":
            return "关闭"
        if value == 1 or value == "1":
            return "开启"
    return value


def diagnostic_status_shape(status: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Return safe field names and types without exporting raw vehicle data."""
    result: dict[str, dict[str, str]] = {}
    for key, _label in safe_status_fields(status):
        value = status[key]
        kind = "boolean" if isinstance(value, bool) else type(value).__name__
        result[key] = {"type": kind}
        if key not in {"odometer", "mileageSurplus", "oilSurplus", "averageFuel"}:
            if value == 0 or value == "0":
                result[key]["binary_code"] = "0"
            elif value == 1 or value == "1":
                result[key]["binary_code"] = "1"
    return result

_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_PRIVATE_SUBSTRINGS = (
    "plate", "mobile", "phone", "imei", "iccid", "imsi", "address",
    "location", "position", "gps", "userid", "deviceid", "vehicleid",
    "carid", "token", "secret", "signature", "email", "owner", "account",
    "license", "identity", "person", "openid", "unionid", "serial",
    "uuid", "auth", "session", "credential", "password", "username",
)


def safe_status_fields(status: dict[str, Any]) -> list[tuple[str, str]]:
    """Expose scalar vehicle fields, excluding identifiers and raw coordinates."""
    fields = []
    for key, value in status.items():
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            continue
        lower = key.lower()
        if (
            lower in {"lat", "lon", "latitude", "longitude", "vin", "id", "sn"}
            or lower.endswith("vin")
            or any(part in lower for part in _PRIVATE_SUBSTRINGS)
            or lower.endswith("id")
        ):
            continue
        if isinstance(value, (dict, list)) or value is None:
            continue
        if isinstance(value, str) and len(value) > 80:
            continue
        if not isinstance(value, (str, int, float, bool)):
            continue
        fields.append((key, LABELS.get(key, f"车况 · {key}")))
    return fields
