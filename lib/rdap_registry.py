"""Select HTTPS domain-query URLs from the bundled official IANA bootstrap.

No redirects, referrals or caller-supplied servers are trusted. The snapshot can
be updated from https://data.iana.org/rdap/dns.json after review.
"""
from functools import lru_cache
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def _domain(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 253 or "." not in value:
        raise ValueError("Informe um domínio completo.")
    if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in value.split(".")):
        raise ValueError("Domínio inválido.")
    if value.rsplit(".", 1)[1].isdigit():
        raise ValueError("Informe um domínio, não um IP.")
    return value


def _safe_base(url):
    if not isinstance(url, str) or len(url) > 1024 or any(ord(c) < 33 or ord(c) == 127 for c in url):
        return False
    try:
        parts = urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.port not in (None, 443) or parts.query or parts.fragment
                or not parts.path.endswith("/") or any(c in url for c in "\\%")):
            return False
        _domain(parts.hostname)
        try:
            ipaddress.ip_address(parts.hostname)
        except ValueError:
            return True
    except ValueError:
        pass
    return False


@lru_cache(maxsize=1)
def bootstrap():
    path = Path(__file__).with_name("rdap-bootstrap.json")
    with path.open("rb") as source:
        content = source.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Catálogo RDAP excessivo.")
    data = json.loads(content)
    if not isinstance(data, dict) or data.get("version") != "1.0" or not isinstance(data.get("services"), list):
        raise ValueError("Catálogo RDAP inválido.")
    services = {}
    for service in data["services"]:
        if (not isinstance(service, list) or len(service) != 2
                or not all(isinstance(group, list) for group in service)):
            raise ValueError("Catálogo RDAP inválido.")
        bases = tuple(url for url in service[1] if _safe_base(url))
        for suffix in service[0]:
            if not isinstance(suffix, str) or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*", suffix):
                raise ValueError("Extensão inválida no catálogo RDAP.")
            services[suffix] = bases
    return str(data.get("publication", "não informada")), services


def domain_url(domain):
    domain = _domain(domain)
    _, services = bootstrap()
    labels = domain.split(".")
    for index in range(len(labels)):
        suffix = ".".join(labels[index:])
        if suffix in services:
            if not services[suffix]:
                raise LookupError("O catálogo desta extensão não fornece um endpoint HTTPS compatível.")
            return services[suffix][0] + "domain/" + domain
    raise LookupError("Extensão sem serviço RDAP no catálogo IANA incluído.")


def permitted_query(url):
    try:
        if not isinstance(url, str):
            return False
        parts = urlsplit(url)
        if parts.query or parts.fragment:
            return False
        domain = parts.path.rsplit("/", 1)[-1]
        return domain_url(domain) == url
    except (ValueError, LookupError, OSError):
        return False
