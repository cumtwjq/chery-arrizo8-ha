"""Copy a previously saved App refresh credential without logging in again."""

from __future__ import annotations

from password_login import REFRESH_FILE
from export_capture import copy_to_clipboard
from vault import _crypt


def main() -> None:
    if not REFRESH_FILE.is_file():
        raise SystemExit("本机尚未保存 App 刷新凭证。")
    refresh = _crypt(REFRESH_FILE.read_bytes(), decrypt=True).decode("utf-8")
    copy_to_clipboard(refresh)
    print("已复制本机加密保存的 App 刷新凭证；请只粘贴到 HA 集成配置页。")


if __name__ == "__main__":
    main()
