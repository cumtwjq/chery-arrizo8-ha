"""Capture and copy one explicit car command without printing secrets."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from export_capture import copy_to_clipboard
from run_capture import MITMDUMP, PORT, ROOT, _port_in_use, _show_ipv4_addresses
from vault import control_vault, load_capture, load_control


CHOICES = {"1": ("find_car", "寻车闪灯"), "2": ("unlock", "车门解锁"), "3": ("lock", "车门上锁")}


def main() -> int:
    if os.name != "nt" or not MITMDUMP.is_file():
        print("请使用完整的 Windows 本地工具包。")
        return 1
    try:
        load_capture()
    except (OSError, ValueError):
        print("请先运行 获取车况请求.cmd，保存同一车辆的车况请求。")
        return 1
    print("选择本次操作：1 寻车闪灯；2 车门解锁；3 车门上锁。")
    choice = input("输入数字后回车：").strip()
    if choice not in CHOICES:
        print("未选择有效操作。")
        return 1
    kind, name = CHOICES[choice]
    if "--copy" in sys.argv:
        try:
            capture = load_control(kind)
            copy_to_clipboard(json.dumps(capture, ensure_ascii=False, separators=(",", ":")))
        except (OSError, ValueError, RuntimeError):
            print("尚无可复制的本机请求，请先抓取该操作。")
            return 1
        print(f"已复制「{name}」请求；请粘贴到 HA 集成「配置」页对应栏目。")
        return 0
    if _port_in_use():
        print("8080 端口已被占用，请先关闭旧代理。")
        return 1
    vault_path = control_vault(kind)
    marker_path = vault_path.with_suffix(".ready.json")
    marker_path.unlink(missing_ok=True)
    started_ns = time.time_ns()
    _show_ipv4_addresses()
    print("iPhone 请使用当前电脑热点，Wi-Fi 代理指向本机地址:8080。")
    print("Safari 打开 http://mitm.it 确认是证书页面。")
    print(f"然后在奇瑞汽车 App 中只操作一次「{name}」，等待窗口提示成功。")
    print("注意：此操作会真实作用于车辆。按 Ctrl+C 可取消；最长等待 15 分钟。")
    environment = {**os.environ, "ARRIZO8_CONTROL_KIND": kind}
    process = subprocess.Popen(
        [str(MITMDUMP), "-q", "-s", str(ROOT / "local_control_capture.py"),
         "--listen-host", "0.0.0.0", "--listen-port", str(PORT)],
        cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        deadline = time.monotonic() + 15 * 60
        while time.monotonic() < deadline:
            if marker_path.is_file():
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                saved_ns = vault_path.stat().st_mtime_ns
                if saved_ns < started_ns - 2_000_000_000 or saved_ns != marker.get("capture_file_modified_ns"):
                    print("加密请求未在本次运行中更新；已停止。")
                    return 1
                capture = load_control(kind)
                copy_to_clipboard(json.dumps(capture, ensure_ascii=False, separators=(",", ":")))
                print(f"已抓取「{name}」成功请求，并复制到剪贴板。")
                print("到 HA 集成的「配置」页粘贴进对应控制请求栏，其他栏可留空。")
                print("完成后关闭 iPhone Wi-Fi 代理，并用普通文字覆盖剪贴板。")
                return 0
            if process.poll() is not None:
                print("代理启动失败，请检查端口 8080。")
                return 1
            time.sleep(0.5)
        print("等待超时；请确认 App 操作成功且请求经过代理。")
        return 1
    except (KeyboardInterrupt, OSError, ValueError, RuntimeError):
        print("已取消或复制到剪贴板失败；请求如已抓到会保存在本机加密存储。")
        return 1
    finally:
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
