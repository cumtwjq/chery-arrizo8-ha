"""Mitmproxy addon: print endpoint and JSON structure without request values.

Usage: mitmdump -q -s capture_summary.py --listen-host <LAN-IP> --listen-port 8080
"""

from __future__ import annotations

import json
import re
import base64
import gzip
import hashlib
import hmac
import itertools
from pathlib import Path
import sys
import threading
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local_tool"))
from inspect_har import safe_path
from vault import VAULT, _crypt, save_capture


SENSITIVE_KEY = re.compile(r"^(?:\d{6,}|[A-HJ-NPR-Z0-9]{17}|[A-Za-z0-9_-]{20,})$", re.I)
_replay_started = False


def shape(value: object, depth: int = 0, key_name: str = "") -> object:
    """Describe container keys and leaf types, never leaf values."""
    if depth >= 4:
        return "..."
    if isinstance(value, dict):
        return {
            "{key}" if SENSITIVE_KEY.fullmatch(str(key)) else str(key): shape(child, depth + 1, str(key))
            for key, child in list(value.items())[:100]
        }
    if isinstance(value, list):
        return [shape(value[0], depth + 1)] if value else []
    if isinstance(value, str) and key_name in {"data", "resData", "parameters"}:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return {"encoding": "json-string", "shape": shape(parsed, depth + 1)}
        except ValueError:
            pass
        if len(value) >= 16 and len(value) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", value):
            return {"encoding": "hex", "bytes": len(value) // 2}
        try:
            decoded = base64.b64decode(value, validate=True)
            if decoded and len(decoded) < 2_000_000:
                try:
                    parsed = json.loads(decoded)
                    if isinstance(parsed, (dict, list)):
                        return {"encoding": "base64-json", "shape": shape(parsed, depth + 1)}
                except (ValueError, UnicodeDecodeError):
                    pass
                return {"encoding": "base64-binary", "bytes": len(decoded)}
        except (ValueError, base64.binascii.Error):
            pass
        return {"encoding": "opaque-string", "chars": len(value)}
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def parse_shape(body: bytes | None) -> object:
    if not body or len(body) > 2_000_000:
        return "none-or-large"
    try:
        return shape(json.loads(body))
    except (ValueError, UnicodeDecodeError):
        return "non-json"


def response(flow) -> None:
    global _replay_started
    host = flow.request.pretty_host.lower()
    if not is_relevant_host(host):
        path = safe_path(flow.request.path.split("?", 1)[0])
        info = {"method": flow.request.method, "host": host, "path": path, "status": flow.response.status_code}
        if re.search(r"login|auth|token|sms|verify|uaa", path, re.I):
            info["request_shape"] = parse_shape(flow.request.raw_content)
            info["response_shape"] = parse_shape(flow.response.raw_content)
        print(json.dumps(info, ensure_ascii=False, separators=(",", ":")), flush=True)
        return
    info = {
        "method": flow.request.method,
        "host": host,
        "path": safe_path(flow.request.path.split("?", 1)[0]),
        "status": flow.response.status_code,
        "request_headers": sorted(flow.request.headers.keys()),
        "request_shape": parse_shape(flow.request.raw_content),
        "response_shape": parse_shape(flow.response.raw_content),
    }
    print(json.dumps(info, ensure_ascii=False, separators=(",", ":")), flush=True)
    if host == "cloudrivechery.mychery.com" and flow.request.path.startswith("/cheryAppData/DKtrans/business"):
        try:
            operation = json.loads(flow.request.raw_content).get("operation")
            if isinstance(operation, str) and re.fullmatch(r"(?:[A-Za-z_][A-Za-z0-9_]{0,63}|\d{1,8})", operation):
                print(json.dumps({"dk_operation": operation}), flush=True)
        except (TypeError, ValueError):
            pass
    if host == "cloudrivechery.mychery.com" and "/vehicleRealtimeData/" in flow.request.path:
        try:
            backup = VAULT.with_name("capture-before-login.dpapi")
            previous = json.loads(_crypt(backup.read_bytes(), decrypt=True))
            previous_token = next(value for key, value in previous["headers"].items() if key.lower() == "access_token")
            current_token = flow.request.headers.get("access_token", "")
            print(json.dumps({"vehicle_token_same_as_before_login": current_token == previous_token}), flush=True)
        except (OSError, KeyError, StopIteration):
            pass
    if (
        not _replay_started
        and host == "cloudrivechery.mychery.com"
        and "/vehicleRealtimeData/" in flow.request.path
    ):
        _replay_started = True
        try:
            capture = {
                "url": flow.request.pretty_url,
                "headers": {
                    key: value for key, value in flow.request.headers.items()
                    if key.lower() in {"access_token", "userid", "content-type", "timestamp", "x-sermant-group"}
                },
                "body": flow.request.raw_content.decode("utf-8"),
            }
            save_capture(capture)
            print(json.dumps({"capture_saved_encrypted": True}), flush=True)
        except (UnicodeDecodeError, OSError, ValueError) as exc:
            print(json.dumps({"capture_saved_encrypted": False, "error_type": type(exc).__name__}), flush=True)
        try:
            original_code = json.loads(flow.response.raw_content).get("resultCode")
        except (ValueError, UnicodeDecodeError, TypeError):
            original_code = None
        try:
            envelope = json.loads(flow.request.raw_content)
            print(json.dumps({
                "vehicle_request_metadata": {
                    "sign_chars": len(envelope.get("sign", "")),
                    "sign_hex": bool(re.fullmatch(r"[0-9a-fA-F]+", envelope.get("sign", ""))),
                    "request_id_chars": len(envelope.get("requestId", "")),
                    "timestamp_chars": len(flow.request.headers.get("timestamp", "")),
                }
            }, separators=(",", ":")), flush=True)
        except (ValueError, TypeError):
            pass
        threading.Thread(
            target=_replay_read_only,
            args=(flow.request.pretty_url, flow.request.method, dict(flow.request.headers), flow.request.raw_content, original_code),
            daemon=True,
        ).start()


def _replay_read_only(url: str, method: str, headers: dict, body: bytes | None, original_code: str | None) -> None:
    """Compare a few in-memory variants of the verified read-only status call."""
    _probe_simple_signs(headers, body)
    headers = {key: value for key, value in headers.items() if key.lower() not in {"host", "content-length", "connection", "accept-encoding"}}
    variants = [("original", headers, body)]
    if body:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict) and "sign" in parsed:
                changed = dict(parsed)
                changed["sign"] = "invalid-test-signature"
                variants.append(("bad_body_sign", headers, json.dumps(changed, separators=(",", ":")).encode()))
            if isinstance(parsed, dict) and "requestId" in parsed:
                changed = dict(parsed)
                changed["requestId"] = "ha-readonly-test"
                variants.append(("changed_request_id", headers, json.dumps(changed, separators=(",", ":")).encode()))
        except (ValueError, UnicodeDecodeError):
            pass
    token_headers = {key: value for key, value in headers.items() if key.lower() != "access_token"}
    variants.append(("no_access_token", token_headers, body))
    cookie_headers = {key: value for key, value in headers.items() if key.lower() != "cookie"}
    variants.append(("no_cookie", cookie_headers, body))
    timestamp_headers = dict(headers)
    for key in timestamp_headers:
        if key.lower() == "timestamp":
            timestamp_headers[key] = "0"
            variants.append(("bad_timestamp", timestamp_headers, body))
            break
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for name, variant_headers, variant_body in variants:
        try:
            request = urllib.request.Request(url, data=variant_body, headers=variant_headers, method=method)
            with opener.open(request, timeout=8) as response:
                raw = response.read(2_000_001)
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                payload = json.loads(raw)
                result = {
                    "replay": name,
                    "http_status": response.status,
                    "same_result_code": payload.get("resultCode") == original_code,
                    "has_data": bool(payload.get("data")),
                }
        except Exception as exc:
            result = {"replay": name, "error_type": type(exc).__name__}
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    time.sleep(300)
    try:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        with opener.open(request, timeout=8) as response:
            payload = json.loads(response.read(2_000_001))
            result = {
                "replay": "original_after_5min",
                "http_status": response.status,
                "same_result_code": payload.get("resultCode") == original_code,
                "has_data": bool(payload.get("data")),
            }
    except Exception as exc:
        result = {"replay": "original_after_5min", "error_type": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)


def _probe_simple_signs(headers: dict, body: bytes | None) -> None:
    """Try common local hashes without exposing any request value."""
    try:
        envelope = json.loads(body or b"")
        target = base64.b64decode(envelope["sign"], validate=True)
        values = {key: str(envelope[key]) for key in ("data", "requestId", "appId", "version") if key in envelope}
        for key in ("access_token", "timestamp", "userId"):
            value = next((value for name, value in headers.items() if name.lower() == key.lower()), None)
            if value:
                values[key] = str(value)
        if len(target) != 32:
            print(json.dumps({"sign_probe": "not_sha256_length"}), flush=True)
            return
        keys = list(values)
        for length in range(1, min(5, len(keys)) + 1):
            for selection in itertools.permutations(keys, length):
                for delimiter in ("", "&", ":", "|"):
                    message = delimiter.join(values[key] for key in selection).encode()
                    candidates = [("sha256", hashlib.sha256(message).digest())]
                    for secret_name in ("access_token", "appId", "userId"):
                        if secret_name in values:
                            candidates.append(("hmac_" + secret_name, hmac.new(values[secret_name].encode(), message, hashlib.sha256).digest()))
                    for algorithm, digest in candidates:
                        if hmac.compare_digest(target, digest):
                            print(json.dumps({"sign_probe": "matched", "algorithm": algorithm, "fields": selection, "delimiter": delimiter}), flush=True)
                            return
        print(json.dumps({"sign_probe": "no_simple_match", "tested_fields": keys}), flush=True)
    except (ValueError, KeyError, TypeError):
        print(json.dumps({"sign_probe": "invalid_envelope"}), flush=True)


def is_relevant_host(host: str) -> bool:
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in ("chery.cn", "mychery.com", "lionaitech.com")
    )


def http_connect(flow) -> None:
    # A CONNECT line exposes only the destination host, even if TLS later fails.
    host = flow.request.host.lower()
    print(json.dumps({"tunnel_host": host}, ensure_ascii=False), flush=True)


def _tls_event(data, event: str) -> None:
    address = getattr(data.context.server, "address", None)
    if address and is_relevant_host(address[0].lower()):
        print(json.dumps({"tls": event, "host": address[0].lower()}), flush=True)


def tls_established_client(data) -> None:
    _tls_event(data, "client_ok")


def tls_failed_client(data) -> None:
    _tls_event(data, "client_failed")


def tls_failed_server(data) -> None:
    _tls_event(data, "server_failed")


def error(flow) -> None:
    request = getattr(flow, "request", None)
    if request is None or not is_relevant_host(request.pretty_host.lower()):
        return
    print(
        json.dumps(
            {
                "method": request.method,
                "host": request.pretty_host.lower(),
                "path": safe_path(request.path.split("?", 1)[0]),
                "status": "network_error",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        flush=True,
    )
