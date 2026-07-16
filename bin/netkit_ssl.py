# Verified-TLS context builder: certifi-backed SSL context with an optional private-CA override.
try:
    import import_declare_test
except ImportError:
    pass

import ssl


def build_verify_context(ca_pem=None):
    if ca_pem and ca_pem.strip():
        return ssl.create_default_context(cadata=ca_pem)
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
