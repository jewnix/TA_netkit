try:
    import import_declare_test
except ImportError:
    pass

import hashlib
import socket
import ssl
import time

import netkit_config
import netkit_logging
from netkit_ssl import build_verify_context
from netkit_targets import parse_targets, run_targets

try:
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, rsa
    from cryptography.x509.oid import ExtensionOID, NameOID
    _CRYPTO_IMPORT_ERROR = None
    _DN_OID = {
        NameOID.COMMON_NAME: ("commonName", "cn"),
        NameOID.ORGANIZATION_NAME: ("organizationName", "org"),
        NameOID.ORGANIZATIONAL_UNIT_NAME: ("organizationalUnitName", "unit"),
        NameOID.LOCALITY_NAME: ("localityName", "locality"),
        NameOID.STATE_OR_PROVINCE_NAME: ("stateOrProvinceName", "state"),
        NameOID.EMAIL_ADDRESS: ("emailAddress", "email"),
    }
    _KU_ATTRS = (
        "digital_signature", "content_commitment", "key_encipherment",
        "data_encipherment", "key_agreement", "key_cert_sign", "crl_sign",
    )
    _PUBKEY_TYPES = (
        (rsa.RSAPublicKey, "RSA"),
        (ec.EllipticCurvePublicKey, "EC"),
        (ed25519.Ed25519PublicKey, "Ed25519"),
        (ed448.Ed448PublicKey, "Ed448"),
        (dsa.DSAPublicKey, "DSA"),
    )
except ImportError as exc:
    _CRYPTO_IMPORT_ERROR = str(exc) or "cryptography"

_DEFAULT_PORT = 443
_TIMEOUT_MS_RANGE = (1, 60000)
_INTERVAL_RANGE_S = (10, 86400)
_GLOBAL_NS = "-"
_CA_CONF = "ta_netkit_certificate_authority"


def _parse_targets(raw):
    return parse_targets(raw, default_port=_DEFAULT_PORT)


def validate_input(definition):
    parameters = definition.parameters
    _parse_targets(parameters.get("targets", ""))
    netkit_config.validate_whole_number(parameters, "timeout_ms", *_TIMEOUT_MS_RANGE)
    netkit_config.validate_interval(parameters, *_INTERVAL_RANGE_S)


def load_cert(der):
    return x509.load_der_x509_certificate(der)


def _serial(number):
    hexed = format(number, "X")
    return ("0" + hexed) if len(hexed) % 2 else hexed


def _dn(name):
    flat = {}
    parts = []
    for attr in name:
        long_name, std = _DN_OID.get(attr.oid, (attr.oid.dotted_string, None))
        parts.append(long_name + "=" + attr.value)
        if std and std not in flat:
            flat[std] = attr.value
    return flat, ", ".join(parts)


def _extension(cert, oid):
    try:
        return cert.extensions.get_extension_for_oid(oid).value
    except x509.ExtensionNotFound:
        return None


def _san(cert):
    ext = _extension(cert, ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    if ext is None:
        return None
    return [str(general_name.value) for general_name in ext] or None


def _eku(cert):
    ext = _extension(cert, ExtensionOID.EXTENDED_KEY_USAGE)
    if ext is None:
        return None
    return [oid.dotted_string for oid in ext] or None


def _key_usage(cert):
    ext = _extension(cert, ExtensionOID.KEY_USAGE)
    if ext is None:
        return None
    names = [attr for attr in _KU_ATTRS if getattr(ext, attr)]
    for attr in ("encipher_only", "decipher_only"):
        try:
            if getattr(ext, attr):
                names.append(attr)
        except ValueError:
            pass
    return names or None


def _is_ca(cert):
    ext = _extension(cert, ExtensionOID.BASIC_CONSTRAINTS)
    if ext is None:
        return None
    return 1 if ext.ca else 0


def _pubkey(cert):
    key = cert.public_key()
    key_type = next(
        (name for cls, name in _PUBKEY_TYPES if isinstance(key, cls)), None)
    return key_type, getattr(key, "key_size", None)


def extract_cert_fields(cert):
    subj_flat, subj_dn = _dn(cert.subject)
    iss_flat, iss_dn = _dn(cert.issuer)
    pubkey_type, pubkey_bits = _pubkey(cert)
    fields = {
        "not_before": int(cert.not_valid_before_utc.timestamp()),
        "not_after": int(cert.not_valid_after_utc.timestamp()),
        "subject": subj_dn or None,
        "subject_cn": subj_flat.get("cn"),
        "issuer": iss_dn or None,
        "issuer_cn": iss_flat.get("cn"),
        "serial": _serial(cert.serial_number),
        "san": _san(cert),
        "self_signed": 1 if (subj_dn and subj_dn == iss_dn) else 0,
        "is_ca": _is_ca(cert),
        "eku": _eku(cert),
        "key_usage": _key_usage(cert),
        "sig_algorithm": cert.signature_algorithm_oid.dotted_string,
        "pubkey_type": pubkey_type,
        "pubkey_bits": pubkey_bits,
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
    host, port = addr
    der, _chain_len, _version, _cipher = _handshake(
        host, port, ssl._create_unverified_context(), timeout_s)
    return der


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
        "key_usage": None,
        "sig_algorithm": None,
        "pubkey_type": None,
        "pubkey_bits": None,
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
                   _fetch_cert=_get_server_cert,
                   _loader=None,
                   now=None):
    if _loader is None:
        _loader = load_cert
    now = time.time() if now is None else now
    result = _base_result(host, port, ca_label)
    der = None
    try:
        der, chain_len, version, cipher = _handshaker(host, port, ctx, timeout_s)
        result["verify_ok"] = 1
        result["chain_len"] = chain_len
        result["tls_version"] = version
        result["cipher"] = cipher
    except ssl.SSLCertVerificationError as exc:
        result["verify_error"] = getattr(exc, "verify_message", None) or str(exc)
        try:
            der = _fetch_cert((host, port), timeout_s)
        except (OSError, ssl.SSLError, ValueError):
            der = None
    except (OSError, ssl.SSLError) as exc:
        result["verify_error"] = str(exc) or type(exc).__name__
    if der is not None:
        result["cert_sha256"] = hashlib.sha256(der).hexdigest()
        try:
            result.update(extract_cert_fields(_loader(der)))
        except Exception as exc:
            if not result["verify_error"]:
                result["verify_error"] = type(exc).__name__
    if result["not_after"] is not None:
        result["days_to_expiry"] = int((result["not_after"] - now) / 86400)
    result["epoch"] = now
    return result


def run_probe(targets_raw, ctx, timeout_ms, ca_label, _inspect=inspect_target):
    return run_targets(
        targets_raw, timeout_ms,
        lambda host, port, timeout_s: _inspect(host, port, ctx, ca_label, timeout_s),
        default_port=_DEFAULT_PORT)


def resolve_ca(session_key, ca_name):
    ca_name = (ca_name or "").strip()
    if not ca_name:
        return None, "certifi"
    from solnlib import conf_manager
    manager = conf_manager.ConfManager(session_key, _GLOBAL_NS)
    stanza = manager.get_conf(_CA_CONF).get(ca_name)
    return stanza.get("ca_certificate"), ca_name


def _stream_one(logger, name, input_item, session_key, event_writer):
    targets_raw = input_item.get("targets", "")
    timeout_ms = netkit_config.clamp_param(
        logger, name, "timeout_ms", int(input_item.get("timeout_ms", 5000)),
        *_TIMEOUT_MS_RANGE)
    ca_pem, ca_label = resolve_ca(session_key, input_item.get("ca"))
    run_epoch = time.time()
    if _CRYPTO_IMPORT_ERROR is not None:
        detail = "cryptography unavailable: " + _CRYPTO_IMPORT_ERROR
        logger.error(netkit_logging.kv(
            event="dependency_missing", input=name, error=detail))
        for host, port in _parse_targets(targets_raw):
            result = _base_result(host, port, ca_label)
            result["verify_error"] = detail
            netkit_logging.emit_event(
                event_writer, name, "netkit:tls", run_epoch, result)
        return
    ctx = build_verify_context(ca_pem)
    run_start = time.perf_counter()
    results = run_probe(targets_raw, ctx, timeout_ms, ca_label)
    verified = netkit_logging.emit_results(
        logger, name, event_writer, "netkit:tls", run_epoch, results,
        ok_field="verify_ok", fail_event="verify_failed",
        fail_fields=("target", "verify_error"),
        debug_fields=("target", "verify_ok"))
    duration_ms = round((time.perf_counter() - run_start) * 1000.0)
    logger.info(netkit_logging.kv(
        event="probe_complete", input=name, targets=len(results),
        verify_ok=verified, duration_ms=duration_ms))


def stream_events(inputs, event_writer):
    netkit_logging.run_input(inputs, event_writer, "tls_error", _stream_one)
