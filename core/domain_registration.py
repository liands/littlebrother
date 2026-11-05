"""DNS nameservers and public registry RDAP data, with independent statuses."""
from dataclasses import asdict
import os

from core.dns_lookup import DNSResult, _display, _timeout, dns_lookup, validate_name, render_lookup
from lib.http import IntegrationError, get_rdap_json
from lib.rdap_registry import bootstrap, domain_url

MAX_ENTITIES = 50
MAX_DEPTH = 3
ROLES = {"registrant": "Titular (registrant)", "registrar": "Registrador (registrar)",
         "technical": "Contato técnico", "administrative": "Contato administrativo", "abuse": "Contato de abuso"}
FIELDS = {"fn": "Nome publicado", "org": "Organização", "email": "Email", "tel": "Telefone",
          "adr": "Endereço publicado", "kind": "Tipo de entidade"}
EVENTS = {"registration": "Registro/criação", "expiration": "Expiração",
          "last changed": "Última alteração", "last update of RDAP database": "Atualização da base RDAP"}
RDAP_STATUS = {"ok": "consulta concluída", "not_checked": "não verificado", "offline": "offline",
               "unsupported": "serviço não disponível no catálogo", "not_found": "domínio não retornado",
               "rate_limited": "limite de consultas atingido", "error": "falha na consulta"}


def _text(value, depth=0):
    if isinstance(value, str):
        return _display(value[:1000])
    if isinstance(value, list) and depth < 3:
        return "; ".join(part for item in value[:16] if (part := _text(item, depth + 1)))[:2000]
    return ""


def _items(value, limit):
    return value[:limit] if isinstance(value, list) else []


def _notices(data):
    notices = []
    for item in _items(data.get("notices"), 10) + _items(data.get("remarks"), 10):
        if isinstance(item, dict):
            text = " — ".join(filter(None, (_text(item.get("title")), _text(item.get("description")))))
            if text:
                notices.append(text)
    return notices


def parse_registration(data, domain):
    if not isinstance(data, dict) or data.get("objectClassName") != "domain" or "errorCode" in data:
        raise ValueError("Resposta RDAP inválida.")
    name = data.get("ldhName") or data.get("unicodeName")
    if validate_name(name, allow_underscore=False) != domain:
        raise ValueError("O registro retornou outro domínio.")
    nameservers = []
    for item in _items(data.get("nameservers"), 256):
        if not isinstance(item, dict):
            raise ValueError("Nameserver RDAP inválido.")
        value = validate_name(item.get("ldhName") or item.get("unicodeName"), allow_underscore=False)
        if value not in nameservers:
            nameservers.append(value)
    contacts, truncated = [], False
    visited = 0

    def entities(items, depth=0):
        nonlocal visited, truncated
        for entity in _items(items, MAX_ENTITIES + 1):
            if visited >= MAX_ENTITIES:
                truncated = True
                return
            visited += 1
            if not isinstance(entity, dict):
                continue
            roles = [_text(value) for value in _items(entity.get("roles"), 10) if isinstance(value, str)]
            fields = {}
            vcard = entity.get("vcardArray")
            if isinstance(vcard, list) and len(vcard) == 2 and vcard[0] == "vcard":
                for row in _items(vcard[1], 100):
                    if isinstance(row, list) and len(row) == 4 and isinstance(row[0], str) and row[0].lower() in FIELDS:
                        key, value = row[0].lower(), _text(row[3])
                        if value and len(fields.get(key, [])) < 5:
                            fields.setdefault(key, []).append(value)
            identifiers = []
            for identifier in _items(entity.get("publicIds"), 10):
                if isinstance(identifier, dict):
                    value = _text(identifier.get("identifier"))
                    if value:
                        identifiers.append({"type": _text(identifier.get("type")), "value": value})
            contacts.append({"roles": roles, "handle": _text(entity.get("handle")), "fields": fields,
                             "public_ids": identifiers, "notices": _notices(entity)})
            children = entity.get("entities")
            if isinstance(children, list) and children:
                if depth < MAX_DEPTH:
                    entities(children, depth + 1)
                else:
                    truncated = True

    entities(data.get("entities"))
    events = [{"action": _text(item.get("eventAction")), "date": _text(item.get("eventDate"))}
              for item in _items(data.get("events"), 50) if isinstance(item, dict)]
    secure = data.get("secureDNS")
    signed = secure.get("delegationSigned") if isinstance(secure, dict) else None
    signed = signed if type(signed) is bool else None
    return {"registered_name": domain, "handle": _text(data.get("handle")),
            "nameservers": sorted(nameservers), "events": events,
            "domain_status": [_text(value) for value in _items(data.get("status"), 50)],
            "delegation_signed": signed, "contacts": contacts, "contacts_truncated": truncated,
            "registrant_published": any("registrant" in item["roles"] and bool(item["fields"]) for item in contacts),
            "redaction_reported": bool(data.get("redacted")), "notices": _notices(data)}


def lookup_registration(domain, timeout=5, *, on_progress=None):
    domain = validate_name(domain, allow_underscore=False)
    if "." not in domain or domain.rsplit(".", 1)[1].isdigit():
        raise ValueError("Informe o domínio registrado completo, sem URL, porta ou www adicional.")
    timeout = _timeout(timeout)
    if on_progress is not None and not callable(on_progress):
        raise ValueError("Callback de progresso inválido.")
    report = {"domain": domain, "dns": {}, "rdap": {"status": "not_checked", "source": None, "message": ""}}
    if os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}:
        report["dns"] = asdict(DNSResult(domain, "NS", "offline", message="Consulta desativada."))
        report["rdap"].update(status="offline", message="Modo offline: consulta desativada.")
        return report
    if on_progress:
        on_progress("Consultando nameservers pelo resolvedor DNS do sistema...")
    report["dns"] = asdict(dns_lookup(domain, "NS", timeout))
    try:
        url = domain_url(domain)
        publication, _ = bootstrap()
    except LookupError as exc:
        report["rdap"].update(status="unsupported", message=str(exc))
        return report
    except (OSError, ValueError):
        report["rdap"].update(status="error", message="Catálogo IANA local indisponível ou inválido.")
        return report
    report["rdap"].update(source=url, bootstrap_publication=publication)
    if on_progress:
        on_progress("Consultando dados públicos no RDAP oficial: " + url)
    try:
        data = get_rdap_json(url)
        parsed = parse_registration(data, domain)
        report["rdap"].update(parsed, status="ok")
    except IntegrationError as exc:
        status = {"http_404": "not_found", "http_429": "rate_limited", "offline": "offline"}.get(exc.code, "error")
        messages = {"http_404": "O registro não retornou este domínio. Confira o domínio registrado; isso não comprova disponibilidade para compra.",
                    "http_429": "O registro limitou as consultas. Tente novamente mais tarde."}
        report["rdap"].update(status=status, message=messages.get(exc.code, str(exc)))
    except (ValueError, TypeError):
        report["rdap"].update(status="error", message="Resposta RDAP inválida ou incompatível com o domínio consultado.")
    return report


def render_registration(report):
    lines = ["Nameservers e registro público — " + report["domain"],
             "", render_lookup(DNSResult(**report["dns"]))]
    rdap = report["rdap"]
    lines += ["", "RDAP — " + RDAP_STATUS[rdap["status"]]]
    if rdap.get("source"):
        lines.append("Fonte oficial: " + rdap["source"])
    if rdap.get("message"):
        lines.append(rdap["message"])
    if rdap["status"] == "ok":
        lines.append("Identificador do domínio: " + (rdap["handle"] or "não publicado"))
        lines.append("Nameservers informados no registro:")
        lines.extend("  " + value for value in rdap["nameservers"])
        if not rdap["nameservers"]:
            lines.append("  Não fornecidos na resposta.")
        dns = report["dns"]
        if dns["status"] == "ok" and rdap["nameservers"]:
            dns_names = {name.rstrip(".").lower() for name in dns["records"]}
            lines.append("Comparação DNS/registro: " + ("listas coincidem." if dns_names == set(rdap["nameservers"]) else "listas diferentes; confira cache, delegação e atualização do registro."))
        lines.append("Status de registro: " + (", ".join(rdap["domain_status"]) or "não publicado"))
        for event in rdap["events"]:
            lines.append(f"{EVENTS.get(event['action'], event['action'])}: {event['date']}")
        signed = rdap["delegation_signed"]
        lines.append("DNSSEC — delegação assinada informada pelo registro: " + ("não informado" if signed is None else "sim" if signed else "não"))
        lines.append("Entidades e contatos publicados (papéis separados):")
        if not rdap["registrant_published"]:
            lines.append("  Titular: dados não fornecidos nesta resposta; podem estar ocultos ou disponíveis somente no registrador.")
        for contact in rdap["contacts"]:
            roles = ", ".join(ROLES.get(role, role) for role in contact["roles"]) or "Papel não informado"
            lines.append("  " + roles + (" | ID: " + contact["handle"] if contact["handle"] else ""))
            for field, values in contact["fields"].items():
                lines.extend(f"    {FIELDS[field]}: {value}" for value in values)
            for identifier in contact["public_ids"]:
                lines.append(f"    Identificador público ({identifier['type']}): {identifier['value']}")
            lines.extend("    Aviso: " + value for value in contact["notices"])
        if rdap["contacts_truncated"]:
            lines.append("  Limite de entidades/profundidade alcançado; lista de contatos parcial.")
        if rdap["redaction_reported"]:
            lines.append("O provedor sinalizou campos ocultados na resposta (redacted).")
        lines.extend("Aviso do registro: " + value for value in rdap["notices"])
    lines += ["", "Dados de titularidade podem estar ocultos ou representar um serviço de privacidade.",
              "Nameserver, registrador e titular têm papéis diferentes; DNSSEC não foi validado criptograficamente.",
              "Consulta NS usa o resolvedor do sistema e seus caches; RDAP consulta o domínio exato, sem buscar contatos por links externos."]
    return "\n".join(lines)


def interactive_nameservers():
    if os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}:
        print("[!] Modo offline: nenhuma consulta DNS ou RDAP foi iniciada.")
        return
    from core.dns_lookup import _input_timeout
    domain = input(" Domínio registrado (ex.: example.com ou empresa.com.br; sem URL): ").strip()
    timeout = _input_timeout()
    print(render_registration(lookup_registration(domain, timeout, on_progress=lambda message: print("[I] " + message, flush=True))))
