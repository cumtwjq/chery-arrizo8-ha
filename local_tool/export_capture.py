"""Copy the encrypted local capture to the owner's clipboard for HA setup."""

from __future__ import annotations

import json
import ctypes
import time

from vault import load_capture


def copy_to_clipboard(value: str) -> None:
    """Place Unicode text on the current interactive Windows clipboard."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
    user32.OpenClipboard.argtypes = (ctypes.c_void_p,)
    user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
    user32.SetClipboardData.restype = ctypes.c_void_p
    raw = value.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(0x0002, len(raw))  # GMEM_MOVEABLE
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    address = kernel32.GlobalLock(handle)
    if not address:
        kernel32.GlobalFree(handle)
        raise ctypes.WinError(ctypes.get_last_error())
    ctypes.memmove(address, raw, len(raw))
    kernel32.GlobalUnlock(handle)
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        kernel32.GlobalFree(handle)
        raise RuntimeError("Windows clipboard is busy")
    try:
        if not user32.EmptyClipboard() or not user32.SetClipboardData(13, handle):
            kernel32.GlobalFree(handle)
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        user32.CloseClipboard()


def main() -> None:
    capture = load_capture()
    copy_to_clipboard(json.dumps(capture, ensure_ascii=False, separators=(",", ":")))
    print("已复制车况请求到剪贴板；请直接粘贴到 HA 的集成配置页，不要发到聊天中。")


if __name__ == "__main__":
    main()
