# HTTPS client helpers: verified-TLS urllib GET and the NetKit User-Agent.
try:
    import import_declare_test
except ImportError:
    pass

import json
import os
import urllib.request

_VERSION_FALLBACK = "1.0.0"
_DEFAULT_TIMEOUT_S = 30.0


def _version(_manifest_path=None):
    path = _manifest_path or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "app.manifest")
    try:
        with open(path) as fh:
            version = json.load(fh)["info"]["id"]["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return _VERSION_FALLBACK
    return version or _VERSION_FALLBACK


def user_agent():
    return "NetKit/" + _version()


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_url(url, context, timeout=_DEFAULT_TIMEOUT_S):
    request = urllib.request.Request(url)
    request.add_header("User-Agent", user_agent())
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context), _NoRedirectHandler())
    return opener.open(request, timeout=timeout)
