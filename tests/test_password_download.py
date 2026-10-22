"""The login helper downloads a complete, valid APK into its tool directory."""

from __future__ import annotations

import base64
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local_tool"))
import password_login


class _Download(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {
            "Content-Length": str(len(data)),
            "ETag": f'"{hashlib.md5(data).hexdigest()}"',
        }

    def geturl(self) -> str:
        return password_login.OFFICIAL_APK_URL

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class PasswordDownloadTest(unittest.TestCase):
    def test_download_once_and_extract_app_key(self):
        key = os.urandom(32)
        source = io.BytesIO()
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("lib/arm64-v8a/libapp.so", b"\0" * 10_000_000 + base64.b64encode(key))
        archive_data = source.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "chery-prod.apk"
            with patch.object(password_login.urllib.request, "urlopen", side_effect=lambda *_args, **_kwargs: _Download(archive_data)) as download:
                self.assertEqual(password_login.ensure_apk(target), target)
                self.assertEqual(password_login.app_key(target), key)
                self.assertEqual(password_login.ensure_apk(target), target)
                self.assertEqual(download.call_count, 1)
                self.assertFalse(list(Path(directory).glob("*.apk.part")))


if __name__ == "__main__":
    unittest.main()
