try:
    import import_declare_test
except ImportError:
    pass

import json
import os

from solnlib import log
from splunklib import modularinput as smi

_ADDON_NAME = "TA_netkit"
_SETTINGS_CONF = "ta_netkit_settings"


def event_time(epoch):
    return "%.3f" % epoch


def kv(**fields):
    parts = []
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, bool):
            raw = "true" if value else "false"
        else:
            raw = str(value)
        escaped = (raw.replace("\\", "\\\\").replace('"', '\\"')
                   .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
        if escaped != raw or " " in escaped or "=" in escaped or escaped == "":
            escaped = '"' + escaped + '"'
        parts.append(key + "=" + escaped)
    return " ".join(parts)


def kv_line(base, fields):
    merged = dict(base)
    for key, value in fields.items():
        merged.setdefault(key, value)
    return kv(**merged)


def get_logger(input_name):
    return log.Logs().get_logger(_ADDON_NAME.lower() + "_" + input_name)


def emit_event(event_writer, stanza, sourcetype, epoch, data):
    event = smi.Event()
    event.stanza = stanza
    event.sourceType = sourcetype
    event.time = event_time(epoch)
    event.data = json.dumps({k: v for k, v in data.items() if v is not None})
    event_writer.write_event(event)


def run_input(inputs, event_writer, error_event, body):
    session_key = inputs.metadata["session_key"]
    for input_name, input_item in inputs.inputs.items():
        name = input_name.split("/")[-1]
        logger = get_logger(name)
        apply_log_level(logger, session_key)
        try:
            body(logger, name, input_item, session_key, event_writer)
        except Exception as exc:
            logger.error(kv(
                event=error_event, input=name, error=str(exc) or type(exc).__name__))


def emit_results(logger, name, event_writer, sourcetype, run_epoch, results, *,
                 ok_field, fail_event, fail_fields, debug_fields=None):
    ok = 0
    for result in results:
        epoch = result.pop("epoch", run_epoch)
        emit_event(event_writer, name, sourcetype, epoch, result)
        payload = result if debug_fields is None else {
            field: result.get(field) for field in debug_fields}
        logger.debug(kv_line({"event": "probe_result", "input": name}, payload))
        if result[ok_field]:
            ok += 1
        else:
            logger.warning(kv_line(
                {"event": fail_event, "input": name},
                {field: result.get(field) for field in fail_fields}))
    return ok


def apply_log_level(logger, session_key):
    if not session_key or not os.environ.get("SPLUNK_HOME"):
        return
    try:
        from solnlib import conf_manager
    except ImportError:
        return
    try:
        level = conf_manager.get_log_level(
            logger=logger,
            session_key=session_key,
            app_name=_ADDON_NAME,
            conf_name=_SETTINGS_CONF,
        )
        logger.setLevel(level)
    except Exception as exc:
        logger.debug(kv(event="log_level_lookup_failed", error=type(exc).__name__))
