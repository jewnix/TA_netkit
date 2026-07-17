try:
    import import_declare_test
except ImportError:
    pass

import http.client
import re
import time
import urllib.parse

import netkit_config
import netkit_http
from netkit_ssl import build_verify_context

_DOWN_URL = "https://speed.cloudflare.com/__down?bytes={0}"
_UP_URL = "https://speed.cloudflare.com/__up"
_MB = 1_000_000
_DOWN_BYTES = 25 * _MB
_UP_BYTES = 5 * _MB
_TIMEOUT_S = 30.0
_MAX_TRANSFER_S = 300.0
_CHUNK_SIZE = 65536
_DOWN_CAP_FACTOR = 2
_PROFILES = {
    "low": (10 * _MB, 2 * _MB),
    "standard": (_DOWN_BYTES, _UP_BYTES),
    "high": (100 * _MB, 20 * _MB),
}
_INTERVAL_FLOOR_S = 300
_INTERVAL_FLOOR_HEAVY_S = 900
_DOWN_MB_RANGE = (1, 500)
_UP_MB_RANGE = (1, 100)


class _ZeroBody:
    def __init__(self, total, deadline=float("inf")):
        self.total = total
        self.deadline = deadline
        self.sent = 0

    def __iter__(self):
        block = b"0" * _CHUNK_SIZE
        while self.sent < self.total:
            if time.perf_counter() >= self.deadline:
                return
            chunk = block[:min(_CHUNK_SIZE, self.total - self.sent)]
            self.sent += len(chunk)
            yield chunk


def _upload(up_bytes, ctx, _factory=None, max_seconds=_MAX_TRANSFER_S):
    parts = urllib.parse.urlsplit(_UP_URL)
    factory = _factory or (lambda: http.client.HTTPSConnection(
        parts.hostname, port=parts.port, context=ctx, timeout=_TIMEOUT_S))
    conn = factory()
    try:
        conn.connect()
        start = time.perf_counter()
        body = _ZeroBody(up_bytes, start + max_seconds)
        conn.request("POST", parts.path, body=body,
                     headers={"User-Agent": netkit_http.user_agent(),
                              "Content-Length": str(up_bytes)})
        if body.sent == up_bytes:
            conn.getresponse().read()
        return time.perf_counter() - start, body.sent
    finally:
        try:
            conn.close()
        except OSError:
            pass


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


def resolve_sizes(input_item, logger=None, name=None):
    profile = _normalize_profile(input_item)
    if profile == "custom":
        try:
            down_mb = int(str(input_item.get("download_mb")).strip())
            up_mb = int(str(input_item.get("upload_mb")).strip())
        except ValueError:
            return _PROFILES["standard"]
        down_mb = netkit_config.clamp_param(
            logger, name, "download_mb", down_mb, *_DOWN_MB_RANGE)
        up_mb = netkit_config.clamp_param(
            logger, name, "upload_mb", up_mb, *_UP_MB_RANGE)
        return (down_mb * _MB, up_mb * _MB)
    return _PROFILES.get(profile, _PROFILES["standard"])


def run_speedtest(_opener=None, _uploader=None, down_bytes=_DOWN_BYTES, up_bytes=_UP_BYTES):
    opener = _opener or netkit_http.open_url
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
        ctx = build_verify_context()
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
                chunk = resp.read(_CHUNK_SIZE)
                if not chunk:
                    break
                received += len(chunk)
                if received >= cap or time.perf_counter() - down_start > _MAX_TRANSFER_S:
                    break
            down_secs = time.perf_counter() - down_start
        result["bytes_received"] = received
        result["download_mbps"] = mbps(received, down_secs)

        up_secs, up_sent = uploader(up_bytes, ctx)
        up_secs = max(up_secs - (result["rtt_ms"] or 0.0) / 1000.0, 1e-6)
        result["bytes_sent"] = up_sent
        result["upload_mbps"] = mbps(up_sent, up_secs)

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
    value = netkit_config.parse_interval(parameters)
    floor = _INTERVAL_FLOOR_HEAVY_S if profile in ("high", "custom") else _INTERVAL_FLOOR_S
    if value < floor:
        raise ValueError(
            "interval must be at least %d seconds for profile %s" % (floor, profile))
    if profile == "custom":
        _validate_mb(parameters, "download_mb", *_DOWN_MB_RANGE)
        _validate_mb(parameters, "upload_mb", *_UP_MB_RANGE)


def stream_events(inputs, event_writer):
    import netkit_logging

    session_key = inputs.metadata["session_key"]
    for input_name, input_item in inputs.inputs.items():
        name = input_name.split("/")[-1]
        logger = netkit_logging.get_logger(name)
        netkit_logging.apply_log_level(logger, session_key)
        try:
            down_bytes, up_bytes = resolve_sizes(input_item, logger, name)
            run_epoch = time.time()
            result = run_speedtest(down_bytes=down_bytes, up_bytes=up_bytes)
            netkit_logging.emit_event(event_writer, name, "netkit:speedtest", run_epoch, result)
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
