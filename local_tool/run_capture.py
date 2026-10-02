"""Run the local proxy, then copy a new captured request to the clipboard."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import time

from export_capture import main as copy_request
from local_capture import READY_MARKER
from vault import VAULT


ROOT = Path(__file__).parent
MITMDUMP = ROOT / "bin" / "mitmdump.exe"
PORT = 8080


def _port_in_use() -> bool:
    """Detect a proxy left behind by an earlier run before starting another."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.5)
        return connection.connect_ex(("127.0.0.1", PORT)) == 0


def _show_ipv4_addresses() -> None:
    command = (
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | "
        "Select-Object -ExpandProperty IPAddress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        addresses = sorted(set(result.stdout.split()))
        if addresses:
            print("本机 IPv4 地址：" + "、".join(addresses))
    except (OSError, subprocess.TimeoutExpired):
        pass


def main() -> int:
    if os.name != "nt":
        print("此工具目前只适用于 Windows。")
        return 1
    if not MITMDUMP.is_file():
        print("缺少 bin/mitmdump.exe；请使用完整的本地工具压缩包。")
        return 1
    if _port_in_use():
        print("端口 8080 已被占用，可能是上次抓取遗留的代理。")
        print("请先关闭旧的抓取窗口或代理，再重新运行；本次没有复制任何请求。")
        return 1
    READY_MARKER.unlink(missing_ok=True)
    started_ns = time.time_ns()
    _show_ipv4_addresses()
    print("iPhone 请连接能访问这台电脑的 Wi-Fi，手动代理填电脑在该网络的 IPv4 地址，端口 8080。")
    print("先用 Safari 打开 http://mitm.it，确认看到证书页面；已有证书无需重装。")
    print("然后打开奇瑞汽车 App，进入艾瑞泽8车况页并刷新一次。等待本窗口提示完成。")
    print("按 Ctrl+C 可停止；最长等待 15 分钟。")
    process = subprocess.Popen(
        [str(MITMDUMP), "-q", "-s", str(ROOT / "local_capture.py"), "--listen-host", "0.0.0.0", "--listen-port", str(PORT)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        deadline = time.monotonic() + 15 * 60
        while time.monotonic() < deadline:
            if READY_MARKER.is_file():
                marker = json.loads(READY_MARKER.read_text(encoding="utf-8"))
                try:
                    saved_ns = VAULT.stat().st_mtime_ns
                except OSError:
                    saved_ns = 0
                if (
                    saved_ns < started_ns - 2_000_000_000
                    or saved_ns != marker.get("capture_file_modified_ns")
                ):
                    print("代理返回了抓取标记，但本机加密请求没有在这次运行中更新。")
                    print("为避免复制旧请求，本次已停止；请检查本地文件权限后重试。")
                    return 1
                print("\n已抓到成功的只读车况请求，并在本机加密保存。")
                print("抓取时间：" + str(marker["captured_at"]))
                if marker.get("token_expires_at"):
                    print("令牌到期时间：" + str(marker["token_expires_at"]))
                if marker.get("token_changed"):
                    print("与上次保存的令牌相比：已变化。")
                else:
                    print("与上次保存的令牌相比：未变化；若是续期，请检查到期时间是否真的延长。")
                try:
                    copy_request()
                except (OSError, RuntimeError, ValueError):
                    print("抓取已加密保存，但复制到剪贴板失败。")
                    print("请稍后双击“复制HA车况请求.cmd”重试，不必重新抓包。")
                    return 1
                print("到 HA 集成的「配置」粘贴剪贴板内容并提交。")
                print("完成后把 iPhone 当前 Wi-Fi 的代理改回「关闭」，并复制普通文字覆盖剪贴板。")
                return 0
            if process.poll() is not None:
                print(f"代理启动失败（退出码 {process.returncode}）。请检查 8080 端口是否被占用。")
                return 1
            time.sleep(0.5)
        print("等待超时。请检查 iPhone 代理、证书页和车况刷新。")
        return 1
    except KeyboardInterrupt:
        print("\n已取消抓取。")
        return 1
    finally:
        if process.poll() is None:
            # The standalone mitmdump launcher can spawn a child process on
            # Windows. Stop the whole tree so port 8080 does not remain open.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
