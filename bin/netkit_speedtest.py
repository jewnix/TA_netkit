try:
    import import_declare_test
except ImportError:
    pass

import http.client
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request

_DOWN_URL = "https://speed.cloudflare.com/__down?bytes={0}"
_UP_URL = "https://speed.cloudflare.com/__up"
_MB = 1_000_000
_DOWN_BYTES = 25 * _MB
_UP_BYTES = 5 * _MB
_TIMEOUT_S = 30.0
_MAX_TRANSFER_S = 300.0
_DOWN_CAP_FACTOR = 2
_VERSION_FALLBACK = "1.0.0"
_PROFILES = {
    "low": (10 * _MB, 2 * _MB),
    "standard": (_DOWN_BYTES, _UP_BYTES),
    "high": (100 * _MB, 20 * _MB),
}
_INTERVAL_FLOOR_S = 300
_INTERVAL_FLOOR_HEAVY_S = 900
_DOWN_MB_RANGE = (1, 500)
_UP_MB_RANGE = (1, 100)


def _version(_manifest_path=None):
    path = _manifest_path or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "app.manifest")
    try:
        with open(path) as fh:
            version = json.load(fh)["info"]["id"]["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return _VERSION_FALLBACK
    return version or _VERSION_FALLBACK


def _user_agent():
    return "NetKit/" + _version()


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(url, ctx):
    request = urllib.request.Request(url)
    request.add_header("User-Agent", _user_agent())
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx), _NoRedirectHandler())
    return opener.open(request, timeout=_TIMEOUT_S)


def _zero_chunks(total, chunk_size=65536):
    block = b"0" * chunk_size
    remaining = total
    while remaining > 0:
        if remaining >= chunk_size:
            yield block
            remaining -= chunk_size
        else:
            yield block[:remaining]
            remaining = 0


def _upload(up_bytes, ctx, _factory=None):
    parts = urllib.parse.urlsplit(_UP_URL)
    factory = _factory or (lambda: http.client.HTTPSConnection(
        parts.hostname, port=parts.port, context=ctx, timeout=_TIMEOUT_S))
    conn = factory()
    try:
        conn.connect()
        start = time.perf_counter()
        conn.request("POST", parts.path, body=_zero_chunks(up_bytes),
                     headers={"User-Agent": _user_agent(),
                              "Content-Length": str(up_bytes)})
        resp = conn.getresponse()
        resp.read()
        return time.perf_counter() - start
    finally:
        try:
            conn.close()
        except OSError:
            pass


def build_ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def mbps(num_bytes, seconds):
    if seconds <= 0:
        return 0.0
    return round((num_bytes * 8) / seconds / 1_000_000, 2)


def parse_server_timing(value):
    out = {"rtt_ms": None, "min_rtt_ms": None}
    if not value:
        return out
    for key, field in (("rtt", "rtt_ms"), ("min_rtt", "min_rtt_ms")):
        match = re.search(r"(?<![a-z_])" + key + r"=(\d+)", value)
        if match:
            out[field] = round(int(match.group(1)) / 1000.0, 2)
    return out


def _normalize_profile(source):
    return str(source.get("profile") or "standard").strip().lower()


def resolve_sizes(input_item):
    profile = _normalize_profile(input_item)
    if profile == "custom":
        try:
            down = int(str(input_item.get("download_mb")).strip()) * _MB
            up = int(str(input_item.get("upload_mb")).strip()) * _MB
        except ValueError:
            return _PROFILES["standard"]
        if down > 0 and up > 0:
            return (down, up)
        return _PROFILES["standard"]
    return _PROFILES.get(profile, _PROFILES["standard"])


def run_speedtest(_opener=None, _uploader=None, down_bytes=_DOWN_BYTES, up_bytes=_UP_BYTES):
    opener = _opener or _open
    uploader = _uploader or _upload
    result = {
        "download_mbps": 0.0,
        "upload_mbps": 0.0,
        "rtt_ms": None,
        "min_rtt_ms": None,
        "bytes_sent": 0,
        "bytes_received": 0,
        "server_location": None,
        "duration_s": 0.0,
        "ok": False,
    }
    start = time.perf_counter()
    try:
        ctx = build_ssl_context()
        received = 0
        down_secs = 0.0
        cap = down_bytes * _DOWN_CAP_FACTOR
        with opener(_DOWN_URL.format(down_bytes), ctx) as resp:
            result["server_location"] = resp.headers.get("colo")
            timing = parse_server_timing(resp.headers.get("server-timing", ""))
            result["rtt_ms"] = timing["rtt_ms"]
            result["min_rtt_ms"] = timing["min_rtt_ms"]
            down_start = time.perf_counter()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                received += len(chunk)
                if received >= cap or time.perf_counter() - down_start > _MAX_TRANSFER_S:
                    break
            down_secs = time.perf_counter() - down_start
        result["bytes_received"] = received
        result["download_mbps"] = mbps(received, down_secs)

        up_secs = uploader(up_bytes, ctx)
        up_secs = max(up_secs - (result["rtt_ms"] or 0.0) / 1000.0, 1e-6)
        result["bytes_sent"] = up_bytes
        result["upload_mbps"] = mbps(up_bytes, up_secs)

        result["ok"] = True
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc) or type(exc).__name__
    result["duration_s"] = round(time.perf_counter() - start, 2)
    return result


def _validate_mb(parameters, field, lo, hi):
    raw = str(parameters.get(field) or "").strip()
    if not (raw.isascii() and raw.isdigit()):
        raise ValueError(field + " must be a whole number of MB")
    value = int(raw)
    if value < lo or value > hi:
        raise ValueError("%s must be between %d and %d" % (field, lo, hi))


def validate_input(definition):
    parameters = definition.parameters
    profile = _normalize_profile(parameters)
    if profile not in ("low", "standard", "high", "custom"):
        raise ValueError("unknown profile: " + profile)
    raw_interval = str(parameters.get("interval") or "").strip()
    if not (raw_interval.isascii() and raw_interval.isdigit()):
        raise ValueError("interval must be a whole number of seconds")
    floor = _INTERVAL_FLOOR_HEAVY_S if profile in ("high", "custom") else _INTERVAL_FLOOR_S
    if int(raw_interval) < floor:
        raise ValueError(
            "interval must be at least %d seconds for profile %s" % (floor, profile))
    if profile == "custom":
        _validate_mb(parameters, "download_mb", *_DOWN_MB_RANGE)
        _validate_mb(parameters, "upload_mb", *_UP_MB_RANGE)


def stream_events(inputs, event_writer):
    import netkit_logging
    from splunklib import modularinput as smi

    session_key = inputs.metadata["session_key"]
    for input_name, input_item in inputs.inputs.items():
        name = input_name.split("/")[-1]
        logger = netkit_logging.get_logger(name)
        netkit_logging.apply_log_level(logger, session_key)
        try:
            down_bytes, up_bytes = resolve_sizes(input_item)
            run_epoch = time.time()
            result = run_speedtest(down_bytes=down_bytes, up_bytes=up_bytes)
            event = smi.Event()
            event.stanza = name
            event.sourceType = "netkit:speedtest"
            event.time = netkit_logging.event_time(run_epoch)
            event.data = json.dumps(result)
            event_writer.write_event(event)
            logger.debug(netkit_logging.kv_line(
                {"event": "speedtest_result", "input": name}, result))
            if result["ok"]:
                logger.info(netkit_logging.kv(
                    event="speedtest_complete", input=name, ok=True,
                    duration_s=result["duration_s"]))
            else:
                logger.error(netkit_logging.kv(
                    event="speedtest_complete", input=name, ok=False,
                    duration_s=result["duration_s"], error=result.get("error")))
        except Exception as exc:
            logger.error(netkit_logging.kv(
                event="speedtest_error", input=name,
                error=str(exc) or type(exc).__name__))
