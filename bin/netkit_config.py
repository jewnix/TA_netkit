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
