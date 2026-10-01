"""Query the saved read-only request and show response key names without values."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local_tool"))
from vault import load_capture


SENSITIVE_KEY = re.compile(r"^(?:\d{6,}|[A-HJ-NPR-Z0-9]{17}|[A-Za-z0-9_-]{20,})$", re.I)


def describe(value: object, depth: int = 0) -> object:
    if depth >= 3:
        return type(value).__name__
    if isinstance(value, dict):
        return {
            ("{id}" if SENSITIVE_KEY.fullmatch(str(key)) else str(key)): describe(child, depth + 1)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [describe(value[0], depth + 1)] if value else []
    return type(value).__name__


def main() -> None:
    capture = load_capture()
    request = Request(
        capture["url"],
        data=capture["body"].encode("utf-8"),
        headers=capture["headers"],
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        envelope = json.load(response)
    data = envelope.get("data")
    status = json.loads(data) if isinstance(data, str) else data
    print(json.dumps(describe(status), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
