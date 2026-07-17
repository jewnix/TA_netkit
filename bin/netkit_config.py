# Input-config validation helpers: whole-number interval parsing and range checks.
try:
    import import_declare_test
except ImportError:
    pass


def parse_interval(parameters):
    raw = str(parameters.get("interval") or "").strip()
    if not (raw.isascii() and raw.isdigit()):
        raise ValueError("interval must be a whole number of seconds")
    return int(raw)


def validate_interval(parameters, lo, hi):
    value = parse_interval(parameters)
    if not lo <= value <= hi:
        raise ValueError("interval must be between %d and %d seconds" % (lo, hi))
    return value


def clamp(value, lo, hi):
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def clamp_param(logger, input_name, param, value, lo, hi):
    used = clamp(value, lo, hi)
    if used != value and logger is not None:
        import netkit_logging
        logger.warning(netkit_logging.kv(
            event="param_clamped", input=input_name, param=param,
            configured=value, clamped=used))
    return used
