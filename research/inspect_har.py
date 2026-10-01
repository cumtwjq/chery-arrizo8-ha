"""Print a value-free endpoint and JSON-key summary from an exported HAR file."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)
LONG_ID = re.compile(r"^[A-Za-z0-9_-]{20,}$")
DIGITS = re.compile(r"^\d{6,}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def safe_path(path: str) -> str:
    segments = path.split("/")
    return "/".join(
        "{id}"
        if (
            VIN.fullmatch(unquote(part))
            or LONG_ID.fullmatch(unquote(part))
            or DIGITS.fullmatch(unquote(part))
            or UUID.fullmatch(unquote(part))
            or any(char in part for char in "%@+=")
        )
        else part
        for part in segments
    )


def json_keys(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    if isinstance(data, dict):
        return ",".join(sorted(str(key) for key in data if isinstance(key, str)))
    if isinstance(data, list):
        return "[array]"
    return ""


def summarize(har: dict) -> list[str]:
    result = []
    for entry in har.get("log", {}).get("entries", []):
        request = entry.get("request", {})
        response = entry.get("response", {})
        url = urlsplit(request.get("url", ""))
        if url.scheme not in {"http", "https"} or not url.hostname:
            continue
        method = request.get("method", "?")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            method = "?"
        req_keys = json_keys(request.get("postData", {}).get("text"))
        res_keys = json_keys(response.get("content", {}).get("text"))
        result.append(
            f"{method} {url.hostname}{safe_path(url.path)} "
            f"request_keys=[{req_keys}] response_keys=[{res_keys}]"
        )
    return sorted(set(result))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python inspect_har.py capture.har")
    har = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print("\n".join(summarize(har)))


if __name__ == "__main__":
    main()
