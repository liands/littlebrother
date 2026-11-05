"""Unified email lookups with isolated exposure and deliverability outcomes."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import math
import os
import re
import time

from core.dns_lookup import validate_name, _display
from core.leaked import leaked
from core.checkleaked import check_email as _checkleaked
from core.checkleaked_view import render_checkleaked
from lib.email_config import load_email_config
from lib.http import IntegrationError, get_json

PROVIDERS = (("HIBP", "hibp_enabled", "HIBP_API_KEY"), ("Hunter", "hunter_enabled", "HUNTER_API_KEY"),
             ("Kickbox", "kickbox_enabled", "KICKBOX_API_KEY"),
             ("CheckLeaked", "checkleaked_enabled", "CHECKLEAKED_API_KEY"))
HUNTER_FLAGS = ("regexp", "gibberish", "disposable", "webmail", "mx_records", "smtp_server", "smtp_check", "accept_all", "block", "role")
KICKBOX_FLAGS = ("role", "free", "disposable", "accept_all")
STATE_LABELS = {"ok": "consulta concluída", "not_configured": "chave não configurada", "disabled": "desativado",
                "offline": "offline", "pending": "verificação em processamento", "error": "consulta não concluída",
                "auth_error": "falha de autenticação/permissão", "rate_limited": "quota/limite atingido",
                "restricted": "consulta restrita pelo provedor", "not_requested": "consulta não solicitada",
                "local_limit": "limite local de tentativas atingido", "cooldown": "aguarde o intervalo entre consultas"}
STATUS_LABELS = {"valid": "válido segundo o provedor", "invalid": "inválido segundo o provedor",
                 "accept_all": "aceita todos os destinatários; caixa individual não confirmada",
                 "webmail": "provedor webmail; caixa individual não confirmada por este status",
                 "disposable": "endereço temporário/descartável", "unknown": "inconclusivo",
                 "deliverable": "entregável segundo o provedor", "undeliverable": "não entregável segundo o provedor",
                 "risky": "entregabilidade de risco"}


def validate_email(value):
    if not isinstance(value, str) or len(value) > 254 or value != value.strip() or value.count("@") != 1:
        raise ValueError("Informe um endereço de email válido, sem URL ou espaços externos.")
    local, domain = value.rsplit("@", 1)
    if (not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local) or local.startswith(".")
            or local.endswith(".") or ".." in local or domain.endswith(".")):
        raise ValueError("Formato de email inválido ou não suportado.")
    domain = validate_name(domain, allow_underscore=False)
    if "." not in domain or domain.rsplit(".", 1)[1].isdigit():
        raise ValueError("Informe um email com domínio completo.")
    email = local + "@" + domain
    if len(email) > 254:
        raise ValueError("Endereço de email excessivo.")
    return email


def _invalid():
    raise IntegrationError("Resposta do provedor inválida ou incompatível com o email consultado.", code="invalid_response")


def _flags(data, names):
    values = {}
    for name in names:
        value = data.get(name)
        if value is not None and type(value) is not bool:
            _invalid()
        values[name] = value
    return values


def _score(value, maximum):
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                              or not math.isfinite(value) or not 0 <= value <= maximum):
        _invalid()
    return value


def _safe(value, secrets=()):
    if not isinstance(value, str):
        return ""
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[chave ocultada]")
    return _display(value[:1000])


def _matching_email(data, email, demo=False):
    if not isinstance(data.get("email"), str):
        _invalid()
    try:
        matched = validate_email(data["email"])
    except ValueError:
        _invalid()
    if not demo and matched.casefold() != email.casefold():
        _invalid()


def _hunter(email, key, config):
    for attempt in range(config["hunter_max_attempts"]):
        try:
            response = get_json("https://api.hunter.io/v2/email-verifier", params={"email": email},
                                headers={"X-API-KEY": key}, read_timeout=25)
            break
        except IntegrationError as exc:
            if exc.code != "http_202":
                raise
            if attempt + 1 >= config["hunter_max_attempts"]:
                raise IntegrationError("Verificação ainda em processamento.", code="pending") from None
            time.sleep(1)
    if not isinstance(response, dict) or response.get("errors") or not isinstance(response.get("data"), dict):
        _invalid()
    data = response["data"]
    status = data.get("status")
    if not isinstance(status, str) or status not in {"valid", "invalid", "accept_all", "webmail", "disposable", "unknown"}:
        _invalid()
    demo = key == "test-api-key"
    _matching_email(data, email, demo)
    flags = _flags(data, HUNTER_FLAGS)
    verification = data.get("verification")
    category = {"valid": "favorable", "invalid": "unfavorable", "accept_all": "risky", "disposable": "risky"}.get(status, "inconclusive")
    if category == "favorable" and (flags["accept_all"] or flags["disposable"] or flags["block"]):
        category = "risky"
    return {"status": status, "category": category, "score": _score(data.get("score"), 100), "flags": flags,
            "verified_at": _safe(verification.get("date"), (key,)) if isinstance(verification, dict) else "", "demo": demo}


def _kickbox(email, key, config):
    data = get_json("https://api.kickbox.com/v2/verify", params={"email": email, "apikey": key,
                    "timeout": config["kickbox_timeout_ms"]})
    if not isinstance(data, dict) or data.get("success") is not True:
        raise IntegrationError("Kickbox não concluiu a consulta.", code="provider_error")
    status = data.get("result")
    if not isinstance(status, str) or status not in {"deliverable", "undeliverable", "risky", "unknown"}:
        _invalid()
    _matching_email(data, email)
    flags = _flags(data, KICKBOX_FLAGS)
    reason = data.get("reason")
    reasons = {"invalid_email", "invalid_domain", "rejected_email", "accepted_email", "low_quality", "low_deliverability",
               "no_connect", "timeout", "invalid_smtp", "unavailable_smtp", "unexpected_error"}
    reason = reason.strip() if isinstance(reason, str) else ""
    reason = reason if reason in reasons else "não informado ou código não reconhecido"
    suggestion = data.get("did_you_mean")
    if suggestion is not None:
        try:
            suggestion = validate_email(suggestion)
        except ValueError:
            _invalid()
    category = {"deliverable": "favorable", "undeliverable": "unfavorable", "risky": "risky", "unknown": "inconclusive"}[status]
    if category == "favorable" and (flags["accept_all"] or flags["disposable"]):
        category = "risky"
    return {"status": status, "category": category, "reason": reason, "score": _score(data.get("sendex"), 1),
            "flags": flags, "suggestion": _safe(suggestion, (key,)),
            "demo": bool(config.get("kickbox_sandbox")) or key.lower().startswith("test_")}


def _hibp(email, key, config):
    records = leaked().email(email, api_key=key)
    return {"breaches": [{name: _safe(record.get(name), (key,)) for name in ("Title", "Domain", "Date")}
                         for record in records[:100]], "count": len(records), "truncated": len(records) > 100}


def _provider(name, email, key, config):
    result = {"provider": name, "state": "ok", "message": "", "data": {}}
    try:
        result["data"] = {"HIBP": _hibp, "Hunter": _hunter, "Kickbox": _kickbox, "CheckLeaked": _checkleaked}[name](email, key, config)
    except IntegrationError as exc:
        code = exc.code
        state = {"http_401": "auth_error", "http_403": "auth_error", "http_402": "rate_limited",
                 "http_429": "rate_limited", "http_451": "restricted", "pending": "pending",
                 "offline": "offline", "local_limit": "local_limit", "cooldown": "cooldown"}.get(code, "error")
        if code == "checkleaked_auth":
            state = "auth_error"
        elif code in {"checkleaked_quota", "checkleaked_cooldown"}:
            state = "rate_limited"
        messages = {"http_401": "Chave inválida ou expirada.", "http_403": "Acesso negado; confira permissões, plano ou quota.",
                    "http_402": "Saldo/plano insuficiente.", "http_429": "Limite de consultas atingido; tente mais tarde.",
                    "http_451": "O provedor restringiu o processamento deste endereço.",
                    "pending": "Hunter ainda processando; nenhuma conclusão de validade foi assumida.",
                    "timeout": "Timeout; o resultado não foi confirmado.", "configuration": "Chave/configuração inválida.",
                    "invalid_response": "Resposta inesperada; o resultado não foi confirmado.",
                    "http_222": "O provedor não concluiu a verificação SMTP.",
                    "local_limit": "CheckLeaked: duas tentativas locais em 24 horas já utilizadas. Não houve nova chamada.",
                    "cooldown": "CheckLeaked: aguarde ao menos 60 segundos desde a última tentativa. Não houve nova chamada.",
                    "checkleaked_auth": "CheckLeaked informou falha de autenticação no corpo da resposta. Confira o Bot Token.",
                    "checkleaked_quota": "CheckLeaked informou limite diário ou créditos insuficientes. O saldo é compartilhado com o site e bots.",
                    "checkleaked_cooldown": "CheckLeaked pediu um intervalo antes de outra busca. Nenhuma repetição automática foi realizada.",
                    "checkleaked_params": "CheckLeaked rejeitou os parâmetros da busca. Foram enviados check=<email informado> e type=email.",
                    "checkleaked_upstream": "CheckLeaked informou indisponibilidade interna ou de uma base consultada. Não houve repetição automática.",
                    "checkleaked_error": "CheckLeaked respondeu HTTP 200 com indicação de falha não reconhecida. Isso não confirma ausência de vazamentos; corpo bruto omitido para proteger dados e credenciais.",
                    "provider_error": "O provedor informou falha. Confira a conta e o saldo no painel."}
        result.update(state=state, message=messages.get(code, "Falha de conexão ou serviço; consulta não concluída."))
    except Exception:
        result.update(state="error", message="Falha isolada nesta integração; consulta não concluída.")
    return result


def lookup_email(email, *, config=None, on_progress=None, consult_checkleaked=False):
    email = validate_email(email)
    if on_progress is not None and not callable(on_progress):
        raise ValueError("Callback de progresso inválido.")
    if type(consult_checkleaked) is not bool:
        raise ValueError("A autorização de consulta CheckLeaked deve ser booleana.")
    report = {"email": email, "providers": []}
    if os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}:
        report["providers"] = [{"provider": name, "state": "offline", "message": "Consultas externas desativadas.", "data": {}}
                               for name, _, _ in PROVIDERS]
        return report
    config = load_email_config() if config is None else config
    results, active = {}, {}
    for name, enabled, key_name in PROVIDERS:
        key = config["keys"].get(key_name, "")
        state = "disabled" if not config.get(enabled, name != "CheckLeaked") else "not_configured" if not key else None
        if name == "CheckLeaked" and state is None and not consult_checkleaked:
            state = "not_requested"
        if state:
            results[name] = {"provider": name, "state": state, "message": "", "data": {}}
        else:
            active[name] = key
    with ThreadPoolExecutor(max_workers=4) as executor:
        pending = {executor.submit(_provider, name, email, key, config): name for name, key in active.items()}
        last_message = time.monotonic()
        while pending:
            done, _ = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
            for future in done:
                name = pending.pop(future)
                try:
                    results[name] = future.result()
                except Exception:
                    results[name] = {"provider": name, "state": "error", "message": "Consulta não concluída.", "data": {}}
                if on_progress:
                    on_progress(name + ": " + STATE_LABELS[results[name]["state"]])
            if pending and time.monotonic() - last_message >= 5:
                if on_progress:
                    on_progress("Aguardando " + ", ".join(pending.values()) + "...")
                last_message = time.monotonic()
    report["providers"] = [results[name] for name, _, _ in PROVIDERS]
    return report


def deliverability_summary(report):
    categories = [item["data"]["category"] for item in report["providers"]
                  if item["provider"] in {"Hunter", "Kickbox"} and item["state"] == "ok" and not item["data"].get("demo")]
    if "favorable" in categories and "unfavorable" in categories:
        return "Provedores divergentes; confira os resultados individuais antes de concluir."
    if "unfavorable" in categories:
        return "Há indicação de endereço não entregável. Confira a fonte e o motivo."
    if "risky" in categories:
        return "Há sinais de risco ou accept-all; existência da caixa individual não confirmada."
    if "favorable" in categories:
        return "Há sinais favoráveis de entregabilidade; isso não garante entrega nem existência permanente da caixa."
    return "Entregabilidade inconclusiva; nenhuma confirmação foi assumida."


def render_email_lookup(report):
    lines = ["Lookup unificado de email — " + report["email"], "", deliverability_summary(report)]
    flag_labels = {"regexp": "Sintaxe aceita", "gibberish": "Aparência aleatória", "disposable": "Descartável",
                   "webmail": "Webmail", "free": "Provedor gratuito", "mx_records": "MX encontrado",
                   "smtp_server": "Servidor SMTP respondeu", "smtp_check": "Verificação SMTP",
                   "accept_all": "Accept-all", "block": "SMTP bloqueou verificação", "role": "Endereço genérico/de função"}
    for item in report["providers"]:
        name, state, data = item["provider"], item["state"], item["data"]
        lines += ["", f"{name} — {STATE_LABELS[state]}"]
        if item["message"]:
            lines.append(item["message"])
        if state != "ok":
            continue
        if name == "CheckLeaked":
            lines.append(render_checkleaked(data))
            continue
        if name == "HIBP":
            if data["count"]:
                lines.append(f"Vazamentos conhecidos retornados: {data['count']}")
                for breach in data["breaches"]:
                    lines.append(f"  {breach['Title']} | {breach['Domain']} | {breach['Date']}")
                if data["truncated"]:
                    lines.append("Exibição limitada aos primeiros 100 registros.")
                lines.append("Revise senhas reutilizadas e ative autenticação de dois fatores.")
            else:
                lines.append("Nenhum vazamento conhecido foi retornado. Isso não comprova ausência de exposição.")
            continue
        if data.get("demo"):
            lines.append("DEMONSTRAÇÃO/SANDBOX: dados de teste; não representa uma verificação real deste endereço.")
        lines.append("Resultado: " + STATUS_LABELS[data["status"]])
        if name == "Hunter":
            lines.append("Score Hunter de entregabilidade (0–100): " + (str(data["score"]) if data["score"] is not None else "não fornecido"))
            if data["verified_at"]:
                lines.append("Data da verificação informada pelo Hunter: " + data["verified_at"])
        else:
            lines.append("Motivo informado: " + data["reason"])
            lines.append("Sendex Kickbox (0–1): " + (str(data["score"]) if data["score"] is not None else "não fornecido"))
            if data["suggestion"]:
                lines.append("Possível correção (não aplicada nem consultada automaticamente): " + data["suggestion"])
        for flag, value in data["flags"].items():
            lines.append(f"  {flag_labels[flag]}: " + ("não fornecido" if value is None else "sim" if value else "não"))
    lines += ["", "Scores são estimativas de entregabilidade do endereço, não reputação global do domínio; não são somados nem promediados.",
              "Exposição em vazamentos e entregabilidade são verificações independentes. Ausência de resultado ou erro não confirma segurança."]
    return "\n".join(lines)
