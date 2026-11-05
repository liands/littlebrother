"""Refresh saved profiles without discarding data after provider failures."""

from copy import deepcopy
from datetime import datetime
from pathlib import Path
import unicodedata

from core.facebookSearchTool import facebookSearchTool
from core.instagramSearchTool import instagramSearchTool
from core.Profiler import Profiler, ProfileError
from core.twitterSearchTool import twitterSearchTool


_PROVIDERS = (
    ("Twitter", twitterSearchTool, "getInfoProfile", {
        "id": "id", "name": "name", "username": "username", "location": "location",
        "urlFound": "url", "description": "description",
    }),
    ("Facebook", facebookSearchTool, "getInfoProfile", {
        "id": "facebookId", "name": "name", "username": "username", "location": "address",
        "job": "job", "affiliations": "affiliations",
    }),
    ("Instagram", instagramSearchTool, "getInfo", {
        "id": "id", "name": "name", "username": "username", "description": "biography",
        "email": "email", "phone": "phone", "location": "adresse", "urlFound": "urlAccount",
    }),
)


def _populated(value):
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None and value != "" and value != [] and value != {}


def _section(data, name):
    for key, value in data.items():
        if isinstance(key, str) and key.casefold() == name.casefold() and isinstance(value, dict):
            return key, value
    return name, {}


def _changes_only(previous, updated):
    changes = {}
    for key, value in updated.items():
        if previous.get(key) == value:
            continue
        if isinstance(value, dict) and isinstance(previous.get(key), dict):
            changes[key] = _changes_only(previous[key], value)
        else:
            changes[key] = deepcopy(value)
    return changes


def _safe_text(value):
    return "".join(character for character in str(value)
                   if unicodedata.category(character) not in {"Cc", "Cf"} or character in "\n\t")


def refresh_profile(data, providers=None):
    """Return a copy, query outcomes and changes; never persist failed results.

    The injectable provider definitions keep this operation testable offline.
    Each adapter must explicitly expose ``success is True`` after its request.
    """
    updated = deepcopy(data)
    outcomes = {}
    changes = []
    _, urls = _section(data, "URL")
    for name, factory, method, attributes in (_PROVIDERS if providers is None else providers):
        account = next((value for key, value in urls.items()
                        if isinstance(key, str) and key.casefold() == name.casefold()), None)
        if not isinstance(account, str) or not account.strip():
            continue
        try:
            adapter = factory()
            getattr(adapter, method)(account.strip())
            if getattr(adapter, "success", False) is not True:
                outcomes[name] = {
                    "status": getattr(adapter, "status", "error"),
                    "error": getattr(adapter, "error", None) or "A consulta não retornou dados confirmados.",
                }
                continue
            key, current = _section(updated, name)
            replacement = deepcopy(current)
            for field, attribute in attributes.items():
                value = getattr(adapter, attribute, None)
                if _populated(value):
                    if replacement.get(field) != value:
                        changes.append("%s: %s atualizado" % (name, field))
                    replacement[field] = deepcopy(value)
            replacement["urlAccount"] = getattr(adapter, "urlAccount", None) or account.strip()
            if replacement != current:
                updated[key] = replacement
            outcomes[name] = {"status": "ok", "error": None}
        except Exception as exc:
            outcomes[name] = {"status": "error", "error": "Falha na integração (%s)." % type(exc).__name__}
    return updated, outcomes, changes


def _report(profile, data, outcomes, generated_at):
    lines = ["LittleBrother — relatório do perfil", "Gerado em: " + generated_at,
             "Perfil: %s (ID %s)" % (profile.get("name", ""), profile.get("id", "")), ""]
    for name, _, _, _ in _PROVIDERS:
        _, section = _section(data, name)
        outcome = outcomes.get(name)
        if not section and not outcome:
            continue
        lines.append(name)
        if outcome:
            lines.append("Consulta: " + outcome["status"])
            if outcome["error"]:
                lines.append("Aviso: " + outcome["error"])
                if section:
                    lines.append("Dados anteriores preservados; não foram confirmados nesta consulta.")
        elif section:
            lines.append("Dados salvos; nenhuma consulta foi realizada.")
        for field, value in section.items():
            if _populated(value):
                lines.append("  %s: %s" % (field, value))
        lines.append("")
    if not outcomes:
        lines.append("Nenhuma conta configurada para consulta.")
    lines.append("Publicações recentes não são consultadas sem uma integração de timeline autorizada.")
    return _safe_text("\n".join(lines)) + "\n"


def profile_report(profile, data, outcomes=None):
    """Build a dated report for both the interactive menu and explicit export."""
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    return _report(profile, data, outcomes or {}, generated_at)


def profilerFunc(profile="", path=""):
    if not isinstance(profile, dict) or not profile.get("file"):
        print("\n[!] Perfil não encontrado.")
        return False
    storage = Profiler(root=path) if path else Profiler()
    try:
        previous = storage.readProfile(profile["file"], path=path)
    except ProfileError as exc:
        print("\n[!] " + str(exc))
        return False
    updated, outcomes, changes = refresh_profile(previous)
    saved = True
    if updated != previous:
        saved = storage.writeProfile(profile["file"], path=path, info=_changes_only(previous, updated))
        if not saved:
            print("\n[!] As atualizações não foram salvas: " + (storage.last_error or "erro de gravação"))
    report = profile_report(profile, updated, outcomes)
    print("\n" + report)
    if changes:
        print("Alterações: " + "; ".join(changes))
    filename = Path(profile["file"]).stem + ".txt"
    try:
        choice = input("\nExportar o relatório como '%s' na pasta de perfis? [s/N]: " % filename)
    except (EOFError, KeyboardInterrupt):
        return saved
    if choice.strip().casefold() in {"s", "sim", "o", "oui", "y", "yes"}:
        if storage.exportText(filename, path=path, data=report):
            print("[+] Relatório exportado: %s" % (Path(path).resolve() / filename))
        else:
            print("[!] Não foi possível exportar: " + (storage.last_error or "erro de gravação"))
            return False
    return saved
