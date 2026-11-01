"""Bounded HTTP capture shared by host and network-isolated container transports."""
import base64
import hashlib
import http.client
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def request(spec):
    url = urlsplit(spec['url'])
    if url.scheme not in ('http', 'https') or not url.hostname or url.username is not None or url.password is not None:
        raise ValueError('Use an HTTP(S) URL without credentials')
    if url.fragment:
        raise ValueError('Fragments are not HTTP request targets')
    timeout = float(spec.get('timeout', 10))
    limit = int(spec.get('max_bytes', 1048576))
    if not 0 < timeout <= 60 or not 0 < limit <= 16777216:
        raise ValueError('Invalid capture bounds')
    context = ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE') or None)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    # Default ProxyHandler honors HTTP(S)_PROXY/NO_PROXY and the platform CA.
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    response = None
    result = {'status': None, 'headers': {}, 'complete': False, 'termination': 'transport_error'}
    raw = bytearray()
    start = time.monotonic()
    deadline = start + timeout
    try:
        body = spec.get('body')
        headers = {'Accept': 'application/json', **spec.get('headers', {})}
        if body is not None:
            body = json.dumps(body, separators=(',', ':')).encode()
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(spec['url'], data=body, headers=headers, method=spec.get('method', 'GET'))
        try:
            response = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        result.update(status=response.status, headers=dict(response.getheaders()))
        # Redirects are recorded, never followed; credentials stay at the configured origin.
        is_stream = spec.get('stream', False)
        while len(raw) <= limit:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result['termination'] = 'observation_window' if is_stream else 'timeout'
                break
            # read1 returns available bytes, so idle SSE does not discard earlier frames.
            fp = response.fp
            sock = getattr(getattr(fp, 'raw', None), '_sock', None)
            if sock is None:  # HTTPError wraps an HTTPResponse.
                sock = getattr(getattr(getattr(fp, 'fp', None), 'raw', None), '_sock', None)
            if sock:
                sock.settimeout(remaining)
            chunk = response.read1(min(65536, limit + 1 - len(raw)))
            if not chunk:
                result.update(complete=True, termination='eof')
                break
            raw.extend(chunk)
            if len(raw) > limit:
                result['termination'] = 'byte_limit'
                break
    except (TimeoutError, socket.timeout):
        result['termination'] = 'observation_window' if spec.get('stream') and result['status'] is not None else 'timeout'
    except (OSError, http.client.HTTPException) as exc:
        result['error_type'] = type(exc).__name__
    finally:
        if response is not None:
            response.close()
    result.update(elapsed_seconds=round(time.monotonic() - start, 4),
                  body_b64=base64.b64encode(raw).decode(),
                  body_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    try:
        result['json'] = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        pass
    return result


if __name__ == '__main__':
    import sys
    print(json.dumps(request(json.load(sys.stdin))))
