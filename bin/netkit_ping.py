try:
    import import_declare_test
except ImportError:
    pass

import concurrent.futures
import socket
import statistics
import time

_MAX_WORKERS = 20
_INTERVAL_RANGE_S = (10, 86400)


def parse_targets(raw):
    if not raw or not raw.strip():
        raise ValueError("targets is empty")
    targets = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError("target missing port: " + chunk)
        host, _, port_str = chunk.rpartition(":")
        host = host.strip()
        port_str = port_str.strip()
        if not host:
            raise ValueError("target missing host: " + chunk)
        if not (port_str.isascii() and port_str.isdigit()):
            raise ValueError("target port not numeric: " + chunk)
        port = int(port_str)
        if port < 1 or port > 65535:
            raise ValueError("target port out of range: " + chunk)
        targets.append((host, port))
    if not targets:
        raise ValueError("no valid targets parsed")
    return targets


def connect_once(host, port, timeout_s, _connector=socket.create_connection):
    start = time.perf_counter()
    try:
        sock = _connector((host, port), timeout=timeout_s)
    except (OSError, UnicodeError):
        return None
    else:
        try:
            sock.close()
        except OSError:
            pass
        return (time.perf_counter() - start) * 1000.0


def summarize(host, port, samples):
    successes = [s for s in samples if s is not None]
    sent = len(samples)
    received = len(successes)
    reachable = received > 0
    failure_pct = round(100.0 * (sent - received) / sent, 1) if sent else 0.0
    if successes:
        min_ms = round(min(successes), 2)
        max_ms = round(max(successes), 2)
        avg_ms = round(sum(successes) / received, 2)
        jitter_ms = round(statistics.stdev(successes), 2) if received > 1 else 0.0
    else:
        min_ms = max_ms = avg_ms = jitter_ms = None
    return {
        "target": host + ":" + str(port),
        "dest": host,
        "port": port,
        "min_ms": min_ms,
        "avg_ms": avg_ms,
        "max_ms": max_ms,
        "jitter_ms": jitter_ms,
        "sent": sent,
        "received": received,
        "failure_pct": failure_pct,
        "reachable": reachable,
    }


def _probe_target(host, port, count, timeout_s, _connector):
    samples = [connect_once(host, port, timeout_s, _connector=_connector)
               for _ in range(count)]
    summary = summarize(host, port, samples)
    summary["epoch"] = time.time()
    return summary


def run_probe(targets_raw, count, timeout_ms, _connector=socket.create_connection):
    timeout_s = timeout_ms / 1000.0
    targets = parse_targets(targets_raw)
    workers = max(1, min(len(targets), _MAX_WORKERS))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(
            lambda target: _probe_target(target[0], target[1], count, timeout_s, _connector),
            targets))


def validate_input(definition):
    parameters = definition.parameters
    parse_targets(parameters.get("targets", ""))
    count = int(parameters.get("count", 4))
    timeout_ms = int(parameters.get("timeout_ms", 2000))
    if count < 1:
        raise ValueError("count must be >= 1")
    if timeout_ms < 1:
        raise ValueError("timeout_ms must be >= 1")
    raw_interval = str(parameters.get("interval") or "").strip()
    if not (raw_interval.isascii() and raw_interval.isdigit()):
        raise ValueError("interval must be a whole number of seconds")
    lo, hi = _INTERVAL_RANGE_S
    if not lo <= int(raw_interval) <= hi:
        raise ValueError("interval must be between %d and %d seconds" % (lo, hi))


def stream_events(inputs, event_writer):
    import json
    import netkit_logging
    from splunklib import modularinput as smi

    session_key = inputs.metadata["session_key"]
    for input_name, input_item in inputs.inputs.items():
        name = input_name.split("/")[-1]
        logger = netkit_logging.get_logger(name)
        netkit_logging.apply_log_level(logger, session_key)
        try:
            targets_raw = input_item.get("targets", "")
            run_epoch = time.time()
            run_start = time.perf_counter()
            count = int(input_item.get("count", 4))
            timeout_ms = int(input_item.get("timeout_ms", 2000))
            summaries = run_probe(targets_raw, count, timeout_ms)
            reachable = 0
            for summary in summaries:
                epoch = summary.pop("epoch", run_epoch)
                event = smi.Event()
                event.stanza = name
                event.sourceType = "netkit:ping"
                event.time = netkit_logging.event_time(epoch)
                event.data = json.dumps(summary)
                event_writer.write_event(event)
                logger.debug(netkit_logging.kv_line(
                    {"event": "probe_result", "input": name}, summary))
                if summary["reachable"]:
                    reachable += 1
                else:
                    logger.warning(netkit_logging.kv(
                        event="target_unreachable", input=name, target=summary["target"],
                        failure_pct=summary["failure_pct"]))
            duration_ms = round((time.perf_counter() - run_start) * 1000.0)
            logger.info(netkit_logging.kv(
                event="probe_complete", input=name, targets=len(summaries),
                reachable=reachable, duration_ms=duration_ms))
        except Exception as exc:
            logger.error(netkit_logging.kv(
                event="ping_error", input=name, error=str(exc) or type(exc).__name__))
