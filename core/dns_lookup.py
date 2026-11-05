"""Bounded DNS queries and direct publication checks for email DNS records."""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import math
import os
import re

import dns.exception
import dns.resolver

RECORD_TYPES = frozenset({"A", "AAAA", "MX", "TXT", "NS", "SOA", "CNAME"})
MAX_SELECTORS = 5


class DNSLookupError(ValueError):
    pass


@dataclass(frozen=True)
class DNSResult:
    host: str
    record_type: str
    status: str
    records: tuple[str, ...] = ()
    ttl: int | None = None
    canonical_name: str | None = None
    message: str = ""


@dataclass(frozen=True)
class PolicyCheck:
    name: str
    query_name: str
    status: str
    records: tuple[str, ...] = ()
    message: str = ""


def validate_name(host, *, allow_underscore=True):
    if (not isinstance(host, str) or not host or host != host.strip() or len(host) > 253
            or any(ord(char) < 33 or ord(char) == 127 for char in host)
            or any(char in host for char in "/\\:@[]%*;|&$`<>\"'")):
        raise DNSLookupError("Informe somente um nome DNS, sem URL, IP, porta ou caminho.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise DNSLookupError("Informe um nome DNS. Consulta reversa de IP não faz parte desta opção.")
    raw = host[:-1] if host.endswith(".") else host
    try:
        value = raw.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise DNSLookupError("Nome DNS inválido.") from None
    pattern = r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?" if allow_underscore else r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if len(value) > 253 or not all(re.fullmatch(pattern, label) for label in value.split(".")):
        raise DNSLookupError("Nome DNS inválido: verifique o domínio e os limites dos rótulos.")
    return value


def _timeout(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 15:
        raise DNSLookupError("O timeout DNS deve estar entre 1 e 15 segundos.")
    return float(value)


def _offline():
    return os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}


def _resolver(timeout):
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = min(timeout, 2.0)
    resolver.lifetime = timeout
    resolver.use_search_by_default = False
    resolver.retry_servfail = False
    return resolver


def dns_lookup(host, record="A", timeout=5, *, resolver=None):
    host = validate_name(host)
    if not isinstance(record, str) or record.upper() not in RECORD_TYPES:
        raise DNSLookupError("Tipo DNS não suportado. Use A, AAAA, MX, TXT, NS, SOA ou CNAME.")
    record = record.upper()
    timeout = _timeout(timeout)
    if _offline():
        return DNSResult(host, record, "offline", message="Modo offline: nenhuma consulta DNS foi iniciada.")
    try:
        resolver = _resolver(timeout) if resolver is None else resolver
        answer = resolver.resolve(host + ".", record, search=False,
                                  lifetime=timeout, raise_on_no_answer=True)
        records = []
        size = 0
        for item in answer:
            # TXT strings are fragments of ONE RR; join before looking for SPF/DKIM/DMARC.
            value = b"".join(item.strings).decode("utf-8", errors="backslashreplace") if record == "TXT" else item.to_text()
            size += len(value)
            if len(records) >= 256 or size > 256 * 1024:
                return DNSResult(host, record, "error", message="Resposta DNS excessiva; a análise não foi concluída.")
            records.append(value)
        if not records:
            return DNSResult(host, record, "no_answer", message="Nenhum registro desse tipo foi retornado para este nome.")
        ttl = answer.rrset.ttl if answer.rrset is not None else None
        canonical = answer.canonical_name.to_text() if answer.canonical_name is not None else None
        return DNSResult(host, record, "ok", tuple(records), ttl, canonical)
    except dns.resolver.NXDOMAIN:
        return DNSResult(host, record, "nxdomain", message="O resolvedor informou que este nome DNS não existe.")
    except dns.resolver.NoAnswer:
        return DNSResult(host, record, "no_answer", message="Nenhum registro desse tipo foi retornado para este nome.")
    except dns.exception.Timeout:
        return DNSResult(host, record, "timeout", message="Timeout DNS. Não foi possível confirmar presença ou ausência do registro.")
    except (dns.resolver.NoNameservers, dns.resolver.NoResolverConfiguration, OSError):
        return DNSResult(host, record, "resolver_error", message="O resolvedor DNS não concluiu a consulta. Verifique a configuração e a conectividade.")
    except dns.exception.DNSException:
        return DNSResult(host, record, "error", message="Resposta ou operação DNS inválida; a consulta não foi concluída.")


def validate_selectors(selectors, domain):
    if isinstance(selectors, str):
        selectors = [item.strip() for item in selectors.split(",")] if selectors.strip() else []
    if not isinstance(selectors, (list, tuple)) or len(selectors) > MAX_SELECTORS:
        raise DNSLookupError("Informe no máximo cinco seletores DKIM separados por vírgula.")
    normalized = []
    for selector in selectors:
        value = validate_name(selector, allow_underscore=False)
        validate_name(value + "._domainkey." + domain)
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _tags(record):
    tags = {}
    for fragment in record.split(";"):
        if not fragment.strip():
            continue
        key, separator, value = fragment.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not key or key in tags:
            return None
        tags[key] = value
    return tags


def _policy(result, name):
    if result.status in {"nxdomain", "no_answer"}:
        return PolicyCheck(name, result.host, "absent", message="Nenhum registro correspondente foi encontrado neste nome consultado.")
    if result.status != "ok":
        return PolicyCheck(name, result.host, result.status, message=result.message)
    if name == "SPF":
        records = tuple(value for value in result.records if re.match(r"^v=spf1(?:\s|$)", value, re.IGNORECASE))
    elif name == "DMARC":
        records = tuple(value for value in result.records if re.match(r"^v=DMARC1(?:\s|;|$)", value))
    else:
        # The DKIM version tag is optional; p= identifies the key material.
        records = tuple(value for value in result.records if re.search(r"(?:^|;)\s*(?:v\s*=\s*DKIM1|p\s*=)", value))
    if not records:
        return PolicyCheck(name, result.host, "absent", message="Não foi identificado um registro correspondente neste nome consultado.")
    if len(records) > 1:
        return PolicyCheck(name, result.host, "multiple", records, "Mais de um registro correspondente foi encontrado; revise a publicação.")
    record = records[0]
    if any(ord(char) < 32 and char != "\t" or ord(char) == 127 for char in record):
        return PolicyCheck(name, result.host, "invalid", records, "O registro contém caracteres de controle inesperados.")
    if name == "SPF":
        return PolicyCheck(name, result.host, "present", records, "SPF publicado. Mecanismos, includes, redirects e limites de consultas não foram avaliados.")
    tags = _tags(record)
    if tags is None:
        return PolicyCheck(name, result.host, "invalid", records, "O registro contém tags repetidas ou estrutura inesperada.")
    if name == "DMARC":
        if tags.get("v") != "DMARC1" or tags.get("p") not in {"none", "quarantine", "reject"}:
            return PolicyCheck(name, result.host, "invalid", records, "Registro identificado, mas a política p= está ausente ou é inválida.")
        message = "DMARC publicado; política p=" + tags["p"] + "."
        if tags["p"] == "none":
            message += " Política de monitoramento; não solicita rejeição nem quarentena."
        return PolicyCheck(name, result.host, "present", records, message)
    if tags.get("v", "DKIM1") != "DKIM1" or "p" not in tags:
        return PolicyCheck(name, result.host, "invalid", records, "Registro DKIM identificado, mas faltam tags válidas de chave/versão.")
    if not tags["p"]:
        return PolicyCheck(name, result.host, "revoked", records, "A chave deste seletor foi revogada (p= vazio).")
    return PolicyCheck(name, result.host, "present", records, "Registro de chave DKIM publicado. A chave criptográfica e as assinaturas de mensagens não foram validadas.")


def check_email_dns(domain, selectors=(), timeout=5):
    domain = validate_name(domain, allow_underscore=False)
    timeout = _timeout(timeout)
    selectors = validate_selectors(selectors, domain)
    # Validate every query name before starting any network request.
    dmarc_name = validate_name("_dmarc." + domain)
    checks = [_policy(dns_lookup(domain, "TXT", timeout), "SPF"),
              _policy(dns_lookup(dmarc_name, "TXT", timeout), "DMARC")]
    if not selectors:
        checks.append(PolicyCheck("DKIM", domain, "not_checked", message="Informe um seletor (s= do cabeçalho DKIM-Signature) para consultar DKIM. Nenhuma descoberta automática foi tentada."))
    for selector in selectors:
        checks.append(_policy(dns_lookup(selector + "._domainkey." + domain, "TXT", timeout), "DKIM"))
    return tuple(checks)


def _display(value):
    return "".join(char if char.isprintable() else "\\x%02x" % ord(char) for char in str(value))


STATUS = {"ok": "consulta concluída", "present": "publicado", "absent": "não encontrado no nome consultado",
          "nxdomain": "nome inexistente", "no_answer": "sem registro desse tipo", "timeout": "timeout",
          "resolver_error": "falha no resolvedor", "error": "erro", "offline": "offline",
          "not_checked": "não verificado", "multiple": "múltiplos registros", "revoked": "chave revogada",
          "invalid": "registro com estrutura inválida"}


def render_lookup(result):
    lines = [f"DNS — {_display(result.host)} | {result.record_type}", "Estado: " + STATUS[result.status]]
    if result.ttl is not None:
        lines.append(f"TTL: {result.ttl} segundos")
    if result.canonical_name:
        lines.append("Nome canônico: " + _display(result.canonical_name))
    if result.message:
        lines.append(result.message)
    lines.extend("  " + _display(value) for value in result.records)
    return "\n".join(lines)


def _input_timeout():
    value = input(" Timeout por consulta em segundos (1–15) [5]: ").strip()
    try:
        return _timeout(float(value) if value else 5)
    except ValueError:
        raise DNSLookupError("Informe um timeout numérico de 1 a 15 segundos.") from None


def interactive_lookup():
    if _offline():
        print("[!] Modo offline: nenhuma consulta DNS foi iniciada.")
        return
    host = input(" Host/nome DNS (sem http://): ").strip()
    record = input(" Tipo [A, AAAA, MX, TXT, NS, SOA, CNAME] [A]: ").strip() or "A"
    timeout = _input_timeout()
    print("[I] Consulta pelo resolvedor DNS configurado no sistema.")
    print(render_lookup(dns_lookup(host, record, timeout)))


def interactive_email_security():
    if _offline():
        print("[!] Modo offline: nenhuma consulta DNS foi iniciada.")
        return
    domain = input(" Domínio de email (sem usuário@): ").strip()
    selectors = input(" Seletores DKIM separados por vírgula (opcional, até 5): ").strip()
    timeout = _input_timeout()
    print("[I] Verificação de publicação DNS direta; não é autenticação de uma mensagem.")
    for check in check_email_dns(domain, selectors, timeout):
        print(f"\n{check.name} — {_display(check.query_name)}: {STATUS[check.status]}")
        print(check.message)
        for value in check.records:
            print("  " + _display(value))
    print("\n[I] DMARC foi consultado no nome exato; herança de política do domínio organizacional não foi avaliada.")
    print("[I] Resultados dependem do resolvedor/caches; DNSSEC e a política efetiva de entrega não foram validados.")
