try:
    import import_declare_test
except ImportError:
    pass

import ssl


def validate_ca_certificate(pem):
    if not pem or not pem.strip():
        raise ValueError("CA certificate is empty")
    try:
        context = ssl.create_default_context(cadata=pem)
    except (ssl.SSLError, ValueError, TypeError) as exc:
        raise ValueError(
            "CA certificate is not valid PEM certificate data: "
            + (str(exc) or type(exc).__name__))
    loaded = context.get_ca_certs()
    if not loaded:
        raise ValueError("No certificates found in CA certificate")
    return len(loaded)
