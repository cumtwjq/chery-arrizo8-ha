"""Copy one combined status/control import for the same owner and vehicle."""

from __future__ import annotations

import json

from export_capture import copy_to_clipboard
from vault import CONTROL_KINDS, load_capture, load_control


def _header(request: dict, name: str) -> str | None:
    return next((str(value) for key, value in request["headers"].items() if key.lower() == name), None)


def _vin(request: dict) -> str:
    return json.loads(json.loads(request["body"])["data"])["vin"]


def main() -> int:
    try:
        status = load_capture()
        controls = {kind: load_control(kind) for kind in CONTROL_KINDS}
        for kind, control in controls.items():
            if (_vin(control) != _vin(status) or
                    _header(control, "userid") != _header(status, "userid") or
                    _header(control, "access_token") != _header(status, "access_token")):
                print(f"{kind} 与当前车况请求不是同一车辆或令牌，请重新抓取对应操作。")
                return 1
        bundle = {"status": status, "controls": controls}
        copy_to_clipboard(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")))
    except (OSError, KeyError, TypeError, ValueError, RuntimeError):
        print("尚未保存完整的车况、寻车、解锁和上锁请求；请先分别抓取。")
        return 1
    print("已复制一份合并请求。到原有奇瑞汽车集成的「配置」页，粘贴进「车况请求 JSON」栏后提交。")
    print("请勿发到聊天或公开位置；用完后复制普通文字覆盖剪贴板。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
