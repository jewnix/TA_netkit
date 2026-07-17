try:
    import import_declare_test
except ImportError:
    pass

import hashlib
import os
import socket
import ssl
import tempfile
import time

import netkit_config
import netkit_targets
from netkit_ssl import build_verify_context

_DEFAULT_PORT = 443
_TIMEOUT_MS_RANGE = (1, 60000)
_INTERVAL_RANGE_S = (10, 86400)
_EXFLAG_CA = 0x10
_GLOBAL_NS = "-"
_CA_CONF = "ta_netkit_certificate_authority"

_DN_KEYS = {
    "commonName": "cn",
    "organizationName": "org",
    "organizationalUnitName": "unit",
    "localityName": "locality",
    "stateOrProvinceName": "state",
    "emailAddress": "email",
}


def parse_targets(raw):
    return netkit_targets.parse_targets(raw, default_port=_DEFAULT_PORT)


def validate_input(definition):
    parameters = definition.parameters
    parse_targets(parameters.get("targets", ""))
    raw_timeout = str(parameters.get("timeout_ms") or "").strip()
    if not (raw_timeout.isascii() and raw_timeout.isdigit()):
        raise ValueError("timeout_ms must be a whole number of milliseconds")
    lo, hi = _TIMEOUT_MS_RANGE
    if not lo <= int(raw_timeout) <= hi:
        raise ValueError("timeout_ms must be between %d and %d" % (lo, hi))
    netkit_config.validate_interval(parameters, *_INTERVAL_RANGE_S)


def decode_pem(pem):
    import _ssl
    handle, path = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(handle, "w") as fh:
            fh.write(pem)
        return _ssl._test_decode_cert(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _epoch(value):
    if not value:
        return None
    try:
        return int(ssl.cert_time_to_seconds(value))
    except (ValueError, TypeError):
        return None


def _dn(sequence):
    flat = {}
    parts = []
    for rdn in sequence or ():
        for key, value in rdn:
            parts.append(key + "=" + value)
            std = _DN_KEYS.get(key)
            if std and std not in flat:
                flat[std] = value
    return flat, ", ".join(parts)


def _san(cert):
    values = [value for _type, value in cert.get("subjectAltName", ())]
    return values or None


def _is_ca(cert):
    flags = cert.get("ex_flags")
    if isinstance(flags, int):
        return 1 if flags & _EXFLAG_CA else 0
    bc = cert.get("basicConstraints")
    if bc is not None:
        text = str(bc).upper()
        if "CA:TRUE" in text:
            return 1
        if "CA:FALSE" in text:
            return 0
    return None


def _eku(cert):
    eku = cert.get("extendedKeyUsage")
    if not eku:
        return None
    if isinstance(eku, (list, tuple)):
        return [str(item) for item in eku]
    return [str(eku)]


def extract_cert_fields(cert):
    subj_flat, subj_dn = _dn(cert.get("subject"))
    iss_flat, iss_dn = _dn(cert.get("issuer"))
    fields = {
        "not_before": _epoch(cert.get("notBefore")),
        "not_after": _epoch(cert.get("notAfter")),
        "subject": subj_dn or None,
        "subject_cn": subj_flat.get("cn"),
        "issuer": iss_dn or None,
        "issuer_cn": iss_flat.get("cn"),
        "serial": cert.get("serialNumber"),
        "san": _san(cert),
        "self_signed": 1 if (subj_dn and subj_dn == iss_dn) else 0,
        "is_ca": _is_ca(cert),
        "eku": _eku(cert),
    }
    for std, value in subj_flat.items():
        if std != "cn":
            fields["subject_" + std] = value
    for std, value in iss_flat.items():
        if std != "cn":
            fields["issuer_" + std] = value
    return fields


def _handshake(host, port, ctx, timeout_s):
    with socket.create_connection((host, port), timeout=timeout_s) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
            try:
                chain = tls.get_verified_chain()
                chain_len = len(chain) if chain else None
            except (AttributeError, ssl.SSLError):
                chain_len = None
            version = tls.version()
            cipher = tls.cipher()
    return der, chain_len, version, (cipher[0] if cipher else None)


def _get_server_cert(addr, timeout_s):
    return ssl.get_server_certificate(addr, timeout=timeout_s)


def _base_result(host, port, ca_label):
    result = {
        "target": host + ":" + str(port),
        "dest": host,
        "port": port,
        "ca": ca_label,
        "not_before": None,
        "not_after": None,
        "days_to_expiry": None,
        "subject": None,
        "subject_cn": None,
        "issuer": None,
        "issuer_cn": None,
        "san": None,
        "serial": None,
        "self_signed": None,
        "is_ca": None,
        "eku": None,
        "chain_len": None,
        "verify_ok": 0,
        "verify_error": None,
        "tls_version": None,
        "cipher": None,
        "cert_sha256": None,
    }
    return result


def inspect_target(host, port, ctx, ca_label, timeout_s,
                   _handshaker=_handshake,
                   _fetch_pem=_get_server_cert,
                   _decoder=None,
                   now=None):
    if _decoder is None:
        _decoder = decode_pem
    now = time.time() if now is None else now
    result = _base_result(host, port, ca_label)
    pem = None
    try:
        der, chain_len, version, cipher = _handshaker(host, port, ctx, timeout_s)
        result["verify_ok"] = 1
        result["chain_len"] = chain_len
        result["tls_version"] = version
        result["cipher"] = cipher
        result["cert_sha256"] = hashlib.sha256(der).hexdigest()
        pem = ssl.DER_cert_to_PEM_cert(der)
    except ssl.SSLCertVerificationError as exc:
        result["verify_error"] = getattr(exc, "verify_message", None) or str(exc)
        try:
            pem = _fetch_pem((host, port), timeout_s)
            result["cert_sha256"] = hashlib.sha256(
                ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
        except (OSError, ssl.SSLError, ValueError):
            pem = None
    except (OSError, ssl.SSLError) as exc:
        result["verify_error"] = str(exc) or type(exc).__name__
    if pem:
        try:
            result.update(extract_cert_fields(_decoder(pem)))
        except Exception as exc:
            if not result["verify_error"]:
                result["verify_error"] = "decode_failed: " + type(exc).__name__
    if result["not_after"] is not None:
        result["days_to_expiry"] = int((result["not_after"] - now) / 86400)
    result["epoch"] = now
    return result


def run_probe(targets_raw, ctx, timeout_ms, ca_label, _inspect=inspect_target):
    timeout_s = timeout_ms / 1000.0
    targets = parse_targets(targets_raw)
    return netkit_targets.run_parallel(
        targets,
        lambda target: _inspect(target[0], target[1], ctx, ca_label, timeout_s))


def resolve_ca(session_key, ca_name):
    ca_name = (ca_name or "").strip()
    if not ca_name:
        return None, "system"
    from solnlib import conf_manager
    manager = conf_manager.ConfManager(session_key, _GLOBAL_NS)
    stanza = manager.get_conf(_CA_CONF).get(ca_name)
    return stanza.get("ca_certificate"), ca_name


def stream_events(inputs, event_writer):
    import netkit_logging

    session_key = inputs.metadata["session_key"]
    for input_name, input_item in inputs.inputs.items():
        name = input_name.split("/")[-1]
        logger = netkit_logging.get_logger(name)
        netkit_logging.apply_log_level(logger, session_key)
        try:
            targets_raw = input_item.get("targets", "")
            timeout_ms = netkit_config.clamp_param(
                logger, name, "timeout_ms", int(input_item.get("timeout_ms", 5000)),
                *_TIMEOUT_MS_RANGE)
            ca_pem, ca_label = resolve_ca(session_key, input_item.get("ca"))
            ctx = build_verify_context(ca_pem)
            run_epoch = time.time()
            run_start = time.perf_counter()
            results = run_probe(targets_raw, ctx, timeout_ms, ca_label)
            verified = 0
            for result in results:
                epoch = result.pop("epoch", run_epoch)
                netkit_logging.emit_event(event_writer, name, "netkit:tls", epoch, result)
                logger.debug(netkit_logging.kv_line(
                    {"event": "probe_result", "input": name},
                    {"target": result["target"], "verify_ok": result["verify_ok"]}))
                if result["verify_ok"]:
                    verified += 1
                else:
                    logger.warning(netkit_logging.kv(
                        event="verify_failed", input=name, target=result["target"],
                        verify_error=result.get("verify_error")))
            duration_ms = round((time.perf_counter() - run_start) * 1000.0)
            logger.info(netkit_logging.kv(
                event="probe_complete", input=name, targets=len(results),
                verify_ok=verified, duration_ms=duration_ms))
        except Exception as exc:
            logger.error(netkit_logging.kv(
                event="tls_error", input=name, error=str(exc) or type(exc).__name__))
