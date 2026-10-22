"""AES-CBC with PKCS#7 padding using Windows CNG; no Python package needed."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys


if sys.platform != "win32":
    raise RuntimeError("Windows CNG is required")

_bcrypt = ctypes.WinDLL("bcrypt")
_HANDLE = ctypes.c_void_p
_PBYTE = ctypes.POINTER(ctypes.c_ubyte)
_DWORD = wintypes.DWORD
_bcrypt.BCryptOpenAlgorithmProvider.argtypes = [ctypes.POINTER(_HANDLE), wintypes.LPCWSTR, wintypes.LPCWSTR, _DWORD]
_bcrypt.BCryptOpenAlgorithmProvider.restype = wintypes.LONG
_bcrypt.BCryptSetProperty.argtypes = [_HANDLE, wintypes.LPCWSTR, _PBYTE, _DWORD, _DWORD]
_bcrypt.BCryptSetProperty.restype = wintypes.LONG
_bcrypt.BCryptGetProperty.argtypes = [_HANDLE, wintypes.LPCWSTR, _PBYTE, _DWORD, ctypes.POINTER(_DWORD), _DWORD]
_bcrypt.BCryptGetProperty.restype = wintypes.LONG
_bcrypt.BCryptGenerateSymmetricKey.argtypes = [_HANDLE, ctypes.POINTER(_HANDLE), _PBYTE, _DWORD, _PBYTE, _DWORD, _DWORD]
_bcrypt.BCryptGenerateSymmetricKey.restype = wintypes.LONG
_bcrypt.BCryptEncrypt.argtypes = [_HANDLE, _PBYTE, _DWORD, _HANDLE, _PBYTE, _DWORD, _PBYTE, _DWORD, ctypes.POINTER(_DWORD), _DWORD]
_bcrypt.BCryptEncrypt.restype = wintypes.LONG
_bcrypt.BCryptDecrypt.argtypes = _bcrypt.BCryptEncrypt.argtypes
_bcrypt.BCryptDecrypt.restype = wintypes.LONG
_bcrypt.BCryptDestroyKey.argtypes = [_HANDLE]
_bcrypt.BCryptCloseAlgorithmProvider.argtypes = [_HANDLE, _DWORD]


def _check(status: int) -> None:
    if status < 0:
        raise OSError(f"Windows CNG AES failed: {status & 0xffffffff:08x}")


def _buffer(data: bytes):
    return (ctypes.c_ubyte * len(data)).from_buffer_copy(data)


def aes_cbc(data: bytes, key: bytes, iv: bytes, *, decrypt: bool = False) -> bytes:
    """Encrypt or decrypt with CNG's built-in PKCS#7 block padding."""
    if len(key) not in (16, 24, 32) or len(iv) != 16:
        raise ValueError("invalid AES key or IV length")
    algorithm = _HANDLE()
    symmetric_key = _HANDLE()
    key_object = None
    _check(_bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(algorithm), "AES", None, 0))
    try:
        mode = _buffer("ChainingModeCBC\0".encode("utf-16-le"))
        _check(_bcrypt.BCryptSetProperty(algorithm, "ChainingMode", mode, len(mode), 0))
        size = _DWORD()
        read = _DWORD()
        _check(_bcrypt.BCryptGetProperty(algorithm, "ObjectLength", ctypes.cast(ctypes.byref(size), _PBYTE), ctypes.sizeof(size), ctypes.byref(read), 0))
        key_object = (ctypes.c_ubyte * size.value)()
        secret = _buffer(key)
        _check(_bcrypt.BCryptGenerateSymmetricKey(algorithm, ctypes.byref(symmetric_key), key_object, len(key_object), secret, len(secret), 0))
        function = _bcrypt.BCryptDecrypt if decrypt else _bcrypt.BCryptEncrypt
        source = _buffer(data)
        initial_iv = _buffer(iv)
        output_size = _DWORD()
        _check(function(symmetric_key, source, len(source), None, initial_iv, len(initial_iv), None, 0, ctypes.byref(output_size), 1))
        output = (ctypes.c_ubyte * output_size.value)()
        second_iv = _buffer(iv)
        _check(function(symmetric_key, source, len(source), None, second_iv, len(second_iv), output, len(output), ctypes.byref(output_size), 1))
        return bytes(output[:output_size.value])
    finally:
        if symmetric_key:
            _bcrypt.BCryptDestroyKey(symmetric_key)
        _bcrypt.BCryptCloseAlgorithmProvider(algorithm, 0)
