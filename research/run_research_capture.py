"""Run one short local capture and report only token metadata."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
MITMDUMP = ROOT.parent / "arrizo8-local-capture" / "bin" / "mitmdump.exe"
DATA = Path(os.environ["LOCALAPPDATA"]) / "Arrizo8HA"
MARKER = DATA / "capture-ready.json"
CODES = DATA / "status-codes.json"


def main() -> int:
    if not MITMDUMP.is_file():
        print("mitmdump.exe missing")
        return 1
    MARKER.unlink(missing_ok=True)
    CODES.unlink(missing_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "local_tool") + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.Popen(
        [
            str(MITMDUMP), "-q", "-s", str(ROOT / "local_tool" / "local_capture.py"),
            "-s", str(ROOT / "research" / "status_codes.py"),
            "--listen-host", "0.0.0.0", "--listen-port", "8080",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    print("Proxy listening on port 8080; waiting for one successful status response.", flush=True)
    try:
        deadline = time.monotonic() + 10 * 60
        while time.monotonic() < deadline:
            if MARKER.is_file():
                time.sleep(1)
                marker = json.loads(MARKER.read_text(encoding="utf-8"))
                print(json.dumps({
                    "captured": True,
                    "token_changed": marker.get("token_changed"),
                    "token_expires_at": marker.get("token_expires_at"),
                    "status_codes_saved": CODES.is_file(),
                }, ensure_ascii=False), flush=True)
                return 0
            if process.poll() is not None:
                print(f"Proxy exited: {process.returncode}", flush=True)
                return 1
            time.sleep(0.5)
        print("Capture timed out", flush=True)
        return 1
    except KeyboardInterrupt:
        print("Capture cancelled", flush=True)
        return 1
    finally:
        if process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
