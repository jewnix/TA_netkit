# Target-list helpers: parse comma-separated host:port lists (port validated via solnlib.net_utils) and fan probes across a thread pool.
try:
    import import_declare_test
except ImportError:
    pass

import concurrent.futures

from solnlib import net_utils

_MAX_WORKERS = 20


def parse_targets(raw, default_port=None):
    if not raw or not raw.strip():
        raise ValueError("targets is empty")
    targets = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            if default_port is None:
                raise ValueError("target missing port: " + chunk)
            host, port = chunk, default_port
        else:
            host, _, port_str = chunk.rpartition(":")
            host = host.strip()
            port_str = port_str.strip()
            if not net_utils.is_valid_port(port_str):
                raise ValueError("target port invalid: " + chunk)
            port = int(port_str)
        if not host:
            raise ValueError("target missing host: " + chunk)
        targets.append((host, port))
    if not targets:
        raise ValueError("no valid targets parsed")
    return targets


def run_parallel(targets, fn):
    workers = max(1, min(len(targets), _MAX_WORKERS))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(fn, targets))


def run_targets(targets_raw, timeout_ms, fn, default_port=None):
    timeout_s = timeout_ms / 1000.0
    targets = parse_targets(targets_raw, default_port=default_port)
    return run_parallel(targets, lambda target: fn(target[0], target[1], timeout_s))
