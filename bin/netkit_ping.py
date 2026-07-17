try:
    import import_declare_test
except ImportError:
    pass

import socket
import statistics
import time

import netkit_config
from netkit_targets import parse_targets, run_parallel

_COUNT_RANGE = (1, 100)
_TIMEOUT_MS_RANGE = (1, 60000)
_INTERVAL_RANGE_S = (10, 86400)


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
    return run_parallel(
        targets,
        lambda target: _probe_target(target[0], target[1], count, timeout_s, _connector))


def validate_input(definition):
    parameters = definition.parameters
    parse_targets(parameters.get("targets", ""))
    count = int(parameters.get("count", 4))
    timeout_ms = int(parameters.get("timeout_ms", 2000))
    lo, hi = _COUNT_RANGE
    if not lo <= count <= hi:
        raise ValueError("count must be between %d and %d" % (lo, hi))
    lo, hi = _TIMEOUT_MS_RANGE
    if not lo <= timeout_ms <= hi:
        raise ValueError("timeout_ms must be between %d and %d" % (lo, hi))
    netkit_config.validate_interval(parameters, *_INTERVAL_RANGE_S)


def stream_events(inputs, event_writer):
    import netkit_logging

    session_key = inputs.metadata["session_key"]
    for input_name, input_item in inputs.inputs.items():
        name = input_name.split("/")[-1]
        logger = netkit_logging.get_logger(name)
        netkit_logging.apply_log_level(logger, session_key)
        try:
            targets_raw = input_item.get("targets", "")
            run_epoch = time.time()
            run_start = time.perf_counter()
            count = netkit_config.clamp_param(
                logger, name, "count", int(input_item.get("count", 4)), *_COUNT_RANGE)
            timeout_ms = netkit_config.clamp_param(
                logger, name, "timeout_ms", int(input_item.get("timeout_ms", 2000)),
                *_TIMEOUT_MS_RANGE)
            summaries = run_probe(targets_raw, count, timeout_ms)
            reachable = 0
            for summary in summaries:
                epoch = summary.pop("epoch", run_epoch)
                netkit_logging.emit_event(event_writer, name, "netkit:ping", epoch, summary)
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
