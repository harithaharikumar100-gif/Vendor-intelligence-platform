"""Validate user-controlled fetch destinations before server-side requests."""
import ipaddress
import socket
from urllib.parse import urlparse


def public_https_url(value, allowed_hosts=None):
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError('An HTTPS URL without credentials or a custom port is required.')
        if allowed_hosts is not None and host not in allowed_hosts:
            raise ValueError('Destination is not in the administrator callback allowlist.')
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError('Private or reserved network destinations are not allowed.')
    except (OSError, ValueError) as error:
        raise ValueError('Destination is unavailable or not an allowed public HTTPS address.') from error
    return value
