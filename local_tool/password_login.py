"""Locally sign in with the owner's official App APK and copy its refresh credential."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile

from export_capture import copy_to_clipboard
from vault import _crypt
from windows_aes import aes_cbc


ROOT = Path.home() / "AppData" / "Local" / "Arrizo8HA"
DEFAULT_APK = Path(__file__).resolve().with_name("chery-prod.apk")
OFFICIAL_APK_URL = "https://img.chery.cn/chery-app-fe/android/chery-prod.apk"
DEVICE_FILE = ROOT / "password-login-device.dpapi"
REFRESH_FILE = ROOT / "app-refresh.dpapi"
BASE_URL = "https://uaa2c.chery.cn/api/v1"
HEADERS = {
    "agent": "ios",
    "appversion": "3.8.1",
    "appversioncode": "26083102",
    "request-channel": "app",
    "x-sermant-group": "",
    "encryptflag": "true",
    "content-type": "application/json; charset=UTF-8",
}


def ensure_apk(apk: Path) -> Path:
    """Download the APK into the extracted tool folder from Chery's own site."""
    if apk.is_file():
        try:
            app_key(apk)
            return apk
        except RuntimeError:
            print("现有 APK 无法识别，将从奇瑞官网重新下载。")
    apk.parent.mkdir(parents=True, exist_ok=True)
    print("正在从奇瑞官网下载奇瑞汽车 APK，首次约需下载数百 MB。")
    temporary: Path | None = None
    try:
        with urllib.request.urlopen(OFFICIAL_APK_URL, timeout=40) as response:
            if not response.geturl().startswith("https://"):
                raise RuntimeError("下载地址未使用 HTTPS，已停止。")
            expected_size = int(response.headers.get("Content-Length") or 0)
            if expected_size and not 10_000_000 <= expected_size <= 1_000_000_000:
                raise RuntimeError("官网返回的 APK 大小异常，已停止。")
            etag = (response.headers.get("ETag") or "").strip('"')
            checksum = hashlib.md5()
            with tempfile.NamedTemporaryFile(dir=apk.parent, suffix=".apk.part", delete=False) as output:
                temporary = Path(output.name)
                total = 0
                next_report = 32 * 1024 * 1024
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    checksum.update(chunk)
                    total += len(chunk)
                    if total > 1_000_000_000:
                        raise RuntimeError("下载文件过大，已停止。")
                    if total >= next_report:
                        print(f"已下载 {total // (1024 * 1024)} MB")
                        next_report += 32 * 1024 * 1024
            if total < 10_000_000 or (expected_size and total != expected_size):
                raise RuntimeError("APK 下载不完整，未用于登录。")
            if re.fullmatch(r"[0-9a-fA-F]{32}", etag) and checksum.hexdigest().lower() != etag.lower():
                raise RuntimeError("APK 下载校验失败，未用于登录。")
        app_key(temporary)
        os.replace(temporary, apk)
        print("官方 APK 已下载到工具目录，下次会直接使用。")
        return apk
    except urllib.error.URLError as err:
        raise RuntimeError("无法从奇瑞官网下载 APK，请检查电脑网络。") from err
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def app_key(apk: Path) -> bytes:
    """Extract the request key from the owner's own official App package."""
    try:
        with zipfile.ZipFile(apk) as archive:
            binary = archive.read("lib/arm64-v8a/libapp.so")
    except (OSError, KeyError, zipfile.BadZipFile) as err:
        raise RuntimeError("无法从 APK 读取登录参数；请检查官方奇瑞汽车 APK 的路径和版本。") from err
    candidates = [base64.b64decode(item) for item in re.findall(rb"[A-Za-z0-9+/]{43}=", binary)]
    candidates = [item for item in candidates if len(item) == 32]
    if len(candidates) != 1:
        raise RuntimeError("当前 APK 的登录参数格式与已验证版本不同，未发送登录请求。")
    return candidates[0]


def device_id() -> str:
    """Keep a stable, owner-local pseudonymous ID across local logins."""
    ROOT.mkdir(parents=True, exist_ok=True)
    if DEVICE_FILE.is_file():
        value = _crypt(DEVICE_FILE.read_bytes(), decrypt=True).decode("ascii")
        if not re.fullmatch(r"[0-9a-f]{32}", value):
            raise RuntimeError("本机设备标识无效；未发送登录请求。")
        return value
    value = uuid.uuid4().hex
    DEVICE_FILE.write_bytes(_crypt(value.encode("ascii"), decrypt=False))
    return value


def encode_request(data: dict, key: bytes) -> bytes:
    iv = os.urandom(16)
    plain = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return base64.b64encode(iv + aes_cbc(plain, key, iv)).replace(b"+", b"-")


def post(path: str, data: dict, key: bytes) -> dict:
    request = urllib.request.Request(BASE_URL + path, data=encode_request(data, key), headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"奇瑞服务器返回 HTTP {err.code}；未保存凭证。") from None
    except urllib.error.URLError:
        raise RuntimeError("无法连接奇瑞服务器；未保存凭证。") from None
    if not isinstance(payload, dict) or payload.get("status") != 200:
        status = payload.get("status") if isinstance(payload, dict) else "unknown"
        raise RuntimeError(f"奇瑞服务器拒绝登录，业务状态 {status}；未保存凭证。")
    result = payload.get("data")
    if not isinstance(result, dict):
        raise RuntimeError("奇瑞服务器没有返回登录数据；未保存凭证。")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="奇瑞汽车本地账号密码登录（实验）")
    parser.add_argument("--apk", type=Path, default=DEFAULT_APK, help="车主自行取得的官方奇瑞汽车 APK")
    args = parser.parse_args()
    try:
        key = app_key(ensure_apk(args.apk))
        identity = device_id()
        print("登录会让同一账号的手机 App 暂时退出；手机重新登录后请核实 HA 凭证仍有效。")
        if input("确认现在登录？输入 yes 继续：").strip().lower() != "yes":
            print("已取消；没有发送登录请求。")
            return 0
        phone = input("奇瑞账号手机号：").strip()
        if not re.fullmatch(r"1\d{10}", phone):
            raise RuntimeError("手机号格式不正确。")
        password = getpass.getpass("奇瑞账号密码（输入不可见）：")
        if not password:
            raise RuntimeError("密码不能为空。")
        challenge = post("/common/secret", {"algorithm": "aes", "username": phone}, key)
        random = challenge.get("random")
        iv = challenge.get("iv")
        if (not isinstance(random, str) or not isinstance(iv, str)
                or len(random.encode()) not in (16, 24, 32) or len(iv.encode()) != 16):
            raise RuntimeError("服务器返回未知的加密参数；没有提交密码。")
        encrypted_password = base64.b64encode(
            aes_cbc((password + "|" + random).encode(), random.encode(), iv.encode())
        ).decode()
        del password
        login = post("/uaa/mobile/token/secret/app", {
            "username": phone,
            "password": encrypted_password,
            "client_id": "bigapp",
            "source": 20,
            "deviceCode": "iPhone",
            "deviceType": "ios",
            "deviceId": identity,
        }, key)
        refresh = login.get("refreshToken")
        if not isinstance(refresh, str) or not refresh:
            raise RuntimeError("登录响应没有 App 刷新凭证；未保存。")
        REFRESH_FILE.write_bytes(_crypt(refresh.encode("utf-8"), decrypt=False))
        copy_to_clipboard(refresh)
        print("登录成功；App 刷新凭证已在本机加密保存并复制到剪贴板。")
        print("请只粘贴到 HA 集成配置页的「App 刷新凭证」，不要发到聊天。")
        return 0
    except (OSError, ValueError, RuntimeError) as err:
        print(f"未完成：{err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
