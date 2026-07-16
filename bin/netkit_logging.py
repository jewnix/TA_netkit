try:
    import import_declare_test
except ImportError:
    pass

import os

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
    from solnlib import log
    return log.Logs().get_logger(_ADDON_NAME + "_" + input_name)


def emit_event(event_writer, stanza, sourcetype, epoch, data):
    import json
    from splunklib import modularinput as smi
    event = smi.Event()
    event.stanza = stanza
    event.sourceType = sourcetype
    event.time = event_time(epoch)
    event.data = json.dumps(data)
    event_writer.write_event(event)


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
