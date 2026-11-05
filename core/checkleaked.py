"""Exact-email CheckLeaked API adapter; metadata only, no credential display.

One request, no retries or pagination. A local conservative rolling budget is
reserved before the network call; it does not know usage on the provider's site.
"""
import hashlib
from pathlib import Path
import sqlite3
import time

from core.dns_lookup import _display
from lib.http import IntegrationError, get_json
import settings

WINDOW = 24 * 60 * 60
DAILY_ATTEMPTS = 2
COOLDOWN = 60
MAX_ROWS = 1000


def _reserve_attempt(key, *, directory=None, now=None):
    root = Path(directory).expanduser().resolve() if directory is not None else settings.data_directory().resolve()
    path = root / "checkleaked_usage.sqlite3"
    instant = time.time() if now is None else now
    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
    connection = None
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise OSError("Invalid quota path")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=1, isolation_level=None)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS attempts (key_id TEXT NOT NULL, used_at REAL NOT NULL)")
        connection.execute("DELETE FROM attempts WHERE used_at <= ?", (instant - WINDOW,))
        rows = connection.execute("SELECT used_at FROM attempts WHERE key_id = ? ORDER BY used_at", (fingerprint,)).fetchall()
        if len(rows) >= DAILY_ATTEMPTS:
            raise IntegrationError("Limite local conservador de duas tentativas em 24 horas atingido.", code="local_limit")
        if rows and instant - rows[-1][0] < COOLDOWN:
            raise IntegrationError("Aguarde ao menos 60 segundos entre tentativas CheckLeaked.", code="cooldown")
        connection.execute("INSERT INTO attempts (key_id, used_at) VALUES (?, ?)", (fingerprint, instant))
        connection.execute("COMMIT")
    except (OSError, sqlite3.Error):
        raise IntegrationError("Controle local de cota indisponível; nenhuma consulta foi enviada.", code="configuration") from None
    finally:
        if connection is not None:
            connection.close()  # Rolls back an uncommitted transaction on rejection.


def _text(value, key):
    if value is None:
        return "não informado"
    if not isinstance(value, str):
        raise IntegrationError("Metadados CheckLeaked inválidos.", code="invalid_response")
    return _display(value.replace(key, "[chave ocultada]")[:300]) or "não informado"


def _provider_failure(response):
    """Classify known error signals without reflecting server text or credentials."""
    parts = []
    for field in ("error", "message", "detail"):
        value = response.get(field)
        if isinstance(value, str):
            parts.append(value[:2000].casefold())
        elif isinstance(value, list):
            parts.extend(item["msg"][:1000].casefold() for item in value[:5]
                         if isinstance(item, dict) and isinstance(item.get("msg"), str))
    message = " ".join(parts)
    if any(term in message for term in ("invalid api key", "invalid key", "invalid token", "unauthorized", "unauthorised", "api-key is required")):
        code = "checkleaked_auth"
    elif any(term in message for term in ("cooldown", "wait between", "wait before", "wait 60", "too fast")):
        code = "checkleaked_cooldown"
    elif any(term in message for term in ("daily limit", "limit exceeded", "quota", "no credits", "insufficient credit", "not enough credit", "credits exhausted", "credit limit")):
        code = "checkleaked_quota"
    elif any(term in message for term in ("invalid query", "invalid type", "invalid email", "wrong params", "missing parameter", "check is required", "validation failed")):
        code = "checkleaked_params"
    elif any(term in message for term in ("upstream", "service unavailable", "internal server", "backend", "temporarily unavailable")):
        code = "checkleaked_upstream"
    else:
        code = "checkleaked_error"
    raise IntegrationError("CheckLeaked retornou uma indicação de falha; texto bruto omitido.", code=code)


def parse_results(response, email, key):
    if not isinstance(response, dict):
        raise IntegrationError("Resposta CheckLeaked inesperada.", code="invalid_response")
    # OpenAPI requires success/result; the official SDK also documents an optional
    # success (including null), results, sources[] and lastBreach. Match either
    # complete result contract, but never mistake an explicit failure for absence.
    if response.get("error") or response.get("success") is False:
        _provider_failure(response)
    success = response.get("success")
    if success is not None and type(success) is not bool:
        raise IntegrationError("Estado CheckLeaked inválido.", code="invalid_response")
    found = response.get("found")
    rows = response.get("result")
    alternative = response.get("results")
    if rows is None:
        rows = alternative
    elif alternative is not None and rows != alternative:
        raise IntegrationError("Listas de resultados CheckLeaked conflitantes.", code="invalid_response")
    if type(found) is not int or found < 0 or not isinstance(rows, list) or (found == 0 and rows):
        raise IntegrationError("Resposta CheckLeaked inesperada.", code="invalid_response")
    sources, fields = {}, set()
    field_names = {"email": "email", "username": "nome de usuário", "password": "senha/credencial (conteúdo omitido)",
                   "hash": "hash (conteúdo omitido)", "phone": "telefone", "ip": "IP", "ip_address": "IP", "name": "nome"}
    for row in rows[:MAX_ROWS]:
        if not isinstance(row, dict):
            raise IntegrationError("Registro CheckLeaked inválido.", code="invalid_response")
        # Late import avoids a dependency cycle with the unified aggregator.
        from core.email_lookup import validate_email
        address = row.get("email")
        if address is not None:
            try:
                address = validate_email(address)
            except ValueError:
                raise IntegrationError("Email do resultado incompatível.", code="invalid_response") from None
            if address.casefold() != email.casefold():
                raise IntegrationError("Resposta fora do email solicitado.", code="invalid_response")
        source = row.get("source")
        metadata = row.get("sources")
        if source is not None:
            if not isinstance(source, dict):
                raise IntegrationError("Fonte CheckLeaked inválida.", code="invalid_response")
            metadata = [source]
        elif metadata is not None and not isinstance(metadata, list):
            raise IntegrationError("Lista de fontes CheckLeaked inválida.", code="invalid_response")
        if not metadata:
            last = row.get("lastBreach")
            if last is not None and not isinstance(last, dict):
                raise IntegrationError("Última fonte CheckLeaked inválida.", code="invalid_response")
            metadata = [last or {}]
        seen = set()
        for source in metadata[:100]:
            if not isinstance(source, dict):
                raise IntegrationError("Fonte CheckLeaked inválida.", code="invalid_response")
            name = _text(source.get("name") or source.get("Name") or source.get("Leak"), key)
            date = _text(source.get("date") or source.get("BreachDate"), key)
            pair = (name, date)
            if pair not in seen:
                sources[pair] = sources.get(pair, 0) + 1
                seen.add(pair)
        fields.update(label for field, label in field_names.items() if row.get(field) not in (None, ""))
    return {"count": found, "rows_received": len(rows), "rows_analyzed": min(len(rows), MAX_ROWS),
            "partial": found > min(len(rows), MAX_ROWS) or len(rows) > MAX_ROWS,
            "sources": [{"name": name, "date": date, "records": count} for (name, date), count in sources.items()],
            "fields": sorted(fields)}


def check_email(email, key, config):
    from core.email_lookup import validate_email
    import os
    email = validate_email(email)
    if os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}:
        raise IntegrationError("Consulta externa desativada.", code="offline")
    if not isinstance(key, str) or not key or len(key) > 8192 or not key.isascii() or any(ord(c) < 33 or ord(c) == 127 for c in key):
        raise IntegrationError("Configure CHECKLEAKED_API_KEY com seu Bot Token.", code="configuration")
    _reserve_attempt(key)
    response = get_json("https://api.checkleaked.cc/api/leak_check", params={"check": email, "type": "email"},
                        headers={"api-key": key})
    # Return a strict whitelist. Raw passwords, hashes and other row values are discarded.
    return parse_results(response, email, key)
