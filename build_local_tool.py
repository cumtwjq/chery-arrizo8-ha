"""Package the self-contained Windows capture tool without owner secrets."""

from __future__ import annotations

import os
import hashlib
from pathlib import Path
from tempfile import gettempdir
from urllib.request import urlretrieve
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).parent
MITMDUMP_CANDIDATES = (
    ROOT.parent / "arrizo8-local-capture" / "bin" / "mitmdump.exe",
    Path(os.environ["TEMP"]) / "arrizo8-mitmproxy" / "bin" / "mitmdump.exe",
)
MITMDUMP = next((path for path in MITMDUMP_CANDIDATES if path.is_file()), None)
DESTINATION = ROOT / "releases" / "arrizo8-local-capture.zip"
LOCAL_TOOL = ROOT / "local_tool"
PYTHON_VERSION = "3.14.7"
PYTHON_ARCHIVE = Path(gettempdir()) / f"arrizo8-python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_SHA256 = "d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15"

if MITMDUMP is None:
    raise SystemExit("mitmdump.exe missing from the verified local installation")
if not PYTHON_ARCHIVE.is_file():
    urlretrieve(PYTHON_URL, PYTHON_ARCHIVE)
if hashlib.sha256(PYTHON_ARCHIVE.read_bytes()).hexdigest() != PYTHON_SHA256:
    raise SystemExit("Python archive checksum does not match python.org")

FILES = [
    "run_capture.py",
    "local_capture.py",
    "vault.py",
    "export_capture.py",
    "获取车况请求.cmd",
    "复制HA车况请求.cmd",
    "本地抓取说明.md",
    "MITMPROXY-LICENSE.txt",
]

DESTINATION.parent.mkdir(exist_ok=True)
with ZipFile(DESTINATION, "w", ZIP_DEFLATED) as archive:
    for name in FILES:
        source = LOCAL_TOOL / name
        if name.lower().endswith(".cmd"):
            # cmd.exe requires CRLF in batch files, including the downloaded ZIP.
            data = source.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            archive.writestr(f"arrizo8-local-capture/{name}", data)
        else:
            archive.write(source, f"arrizo8-local-capture/{name}")
    archive.write(MITMDUMP, "arrizo8-local-capture/bin/mitmdump.exe")
    with ZipFile(PYTHON_ARCHIVE) as python_archive:
        python_members = python_archive.namelist()
        for member in python_members:
            data = python_archive.read(member)
            if member == "python314._pth":
                data = b"python314.zip\r\n.\r\n..\r\n"
            archive.writestr(f"arrizo8-local-capture/python/{member}", data)

print(f"Built {DESTINATION.name} with {len(FILES) + 1 + len(python_members)} files")
