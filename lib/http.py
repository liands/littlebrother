"""Bounded HTTPS access for explicitly supported services."""
from __future__ import annotations

import json
import os
import time
from urllib.parse import urlsplit

import requests
from urllib3.exceptions import HTTPError as TransportError, ReadTimeoutError

API_HOSTS = frozenset({
    "api.x.com", "api.twitter.com", "graph.facebook.com", "graph.instagram.com",
    "haveibeenpwned.com", "api.pwnedpasswords.com", "ipwho.is", "api.mylnikov.org",
    "crt.sh", "api.certspotter.com", "api.hackertarget.com",
    "api.hunter.io", "api.kickbox.com",
    "api.checkleaked.cc",
})
MEDIA_DOMAINS = ("cdninstagram.com", "fbcdn.net", "twimg.com")
MAX_BYTES = 20 * 1024 * 1024
TIMEOUT = (5, 12)
DEADLINE_SECONDS = 30


class IntegrationError(Exception):
    def __init__(self, message, code="error", status_code=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def validate_url(url):
    if not isinstance(url, str) or not url or len(url) > 8192:
        raise IntegrationError("URL inválida.", code="invalid_input")
    if any(ord(c) < 33 or ord(c) == 127 for c in url) or "\\" in url:
        raise IntegrationError("URL contém caracteres inválidos.", code="invalid_input")
    try:
        parts = urlsplit(url)
        valid = (parts.scheme == "https" and parts.hostname and parts.username is None
                 and parts.password is None and parts.port in (None, 443) and not parts.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise IntegrationError("Use uma URL HTTPS sem credenciais, fragmento ou porta alternativa.", code="invalid_input")
    return url


def _allowed(url, media=False, rdap=False):
    validate_url(url)
    if rdap:
        from lib.rdap_registry import permitted_query
        if permitted_query(url):
            return
        raise IntegrationError("Consulta RDAP fora do catálogo IANA ou com caminho inválido.", code="blocked_host")
    host = urlsplit(url).hostname.lower()
    if host in API_HOSTS:
        return
    if media and any(host == domain or host.endswith("." + domain) for domain in MEDIA_DOMAINS):
        return
    raise IntegrationError("Domínio não permitido para requisições automáticas.", code="blocked_host")


def _read(url, *, params=None, headers=None, max_bytes=2 * 1024 * 1024, media=False, rdap=False, read_timeout=None):
    _allowed(url, media=media, rdap=rdap)
    if os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in ("1", "true", "yes"):
        raise IntegrationError("Modo offline: consulta externa desativada.", code="offline")
    if not isinstance(max_bytes, int) or not 1 <= max_bytes <= MAX_BYTES:
        raise IntegrationError("Limite de download inválido.", code="invalid_input")
    if read_timeout is not None and (type(read_timeout) is not int or not 1 <= read_timeout <= 25):
        raise IntegrationError("Timeout de leitura inválido.", code="invalid_input")
    timeout = TIMEOUT if read_timeout is None else (TIMEOUT[0], read_timeout)
    request_headers = {"User-Agent": "LittleBrother-Local/7.0", "Accept": "application/json", "Accept-Encoding": "identity"}
    request_headers.update(headers or {})
    started = time.monotonic()
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get(url, params=params, headers=request_headers, timeout=timeout,
                             allow_redirects=False, stream=True, verify=True) as response:
                status = response.status_code
                if 300 <= status < 400:
                    raise IntegrationError("O serviço redirecionou a consulta; integração não prosseguiu.", code="redirect", status_code=status)
                if status != 200:
                    messages = {401: "Credencial ausente, inválida ou expirada.",
                                403: "O serviço negou acesso; verifique permissões e plano.",
                                404: "Recurso não encontrado no serviço.",
                                429: "Limite de consultas atingido. Tente novamente mais tarde."}
                    raise IntegrationError(messages.get(status, "Serviço indisponível ou resposta HTTP inesperada."),
                                           code=f"http_{status}", status_code=status)
                if response.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
                    raise IntegrationError("O serviço enviou uma codificação não solicitada.", code="invalid_response")
                length = response.headers.get("Content-Length")
                if length:
                    try:
                        if int(length) > max_bytes:
                            raise IntegrationError("Resposta excede o limite de tamanho.", code="too_large")
                    except ValueError:
                        raise IntegrationError("Tamanho de resposta inválido.", code="invalid_response") from None
                chunks = []
                total = 0
                while True:
                    if time.monotonic() - started > DEADLINE_SECONDS:
                        raise IntegrationError("Tempo total da consulta excedido.", code="timeout")
                    # read1 returns available data instead of waiting to fill a chunk.
                    chunk = response.raw.read1(16384, decode_content=False)
                    if time.monotonic() - started > DEADLINE_SECONDS:
                        raise IntegrationError("Tempo total da consulta excedido.", code="timeout")
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise IntegrationError("Resposta excede o limite de tamanho.", code="too_large")
                    chunks.append(chunk)
                return b"".join(chunks)
    except (requests.exceptions.Timeout, ReadTimeoutError):
        raise IntegrationError("O serviço não respondeu dentro do limite de tempo.", code="timeout") from None
    except requests.exceptions.SSLError:
        raise IntegrationError("Não foi possível validar o certificado HTTPS do serviço.", code="tls_error") from None
    except (requests.exceptions.RequestException, TransportError):
        # Exceptions can contain a URL, email or token. Do not expose their text.
        raise IntegrationError("Falha de conexão com o serviço.", code="network_error") from None


def get_bytes(url, *, params=None, headers=None, max_bytes=10 * 1024 * 1024):
    return _read(url, params=params, headers=headers, max_bytes=max_bytes, media=True)


def get_text(url, *, params=None, headers=None, read_timeout=None):
    options = {"read_timeout": read_timeout} if read_timeout is not None else {}
    data = _read(url, params=params, headers=headers, **options)
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IntegrationError("O serviço retornou texto em formato inesperado.", code="invalid_response") from None


def get_json(url, *, params=None, headers=None, read_timeout=None):
    try:
        options = {"read_timeout": read_timeout} if read_timeout is not None else {}
        data = json.loads(get_text(url, params=params, headers=headers, **options))
    except (ValueError, RecursionError):
        raise IntegrationError("O serviço retornou JSON inválido.", code="invalid_response") from None
    if not isinstance(data, (dict, list)):
        raise IntegrationError("O serviço retornou uma estrutura inesperada.", code="invalid_response")
    return data


def get_rdap_json(url):
    """Only exact HTTPS /domain/name queries selected from the IANA snapshot."""
    raw = _read(url, rdap=True, headers={"Accept": "application/rdap+json, application/json"})
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, RecursionError):
        raise IntegrationError("O registro retornou JSON inválido.", code="invalid_response") from None
    if not isinstance(data, dict):
        raise IntegrationError("O registro retornou uma estrutura inesperada.", code="invalid_response")
    return data
