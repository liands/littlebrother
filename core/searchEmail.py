"""Existing email menu entry, aggregating configured verification services."""
import os
from core.email_lookup import lookup_email, render_email_lookup, validate_email
from lib.email_config import configuration_path, load_email_config


def SearchEmail():
    if os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}:
        print("[!] Modo offline: nenhuma consulta de email foi iniciada.")
        return
    email = validate_email(input(" Email próprio ou autorizado: ").strip())
    config = load_email_config()
    consult_checkleaked = False
    if config["checkleaked_enabled"] and config["keys"]["CHECKLEAKED_API_KEY"]:
        answer = input(" Consultar também CheckLeaked? Pode consumir 1 das 2 buscas diárias [s/N]: ").strip().casefold()
        if answer not in {"", "s", "sim", "y", "yes", "n", "não", "nao", "no"}:
            raise ValueError("Responda s ou n para a consulta CheckLeaked.")
        consult_checkleaked = answer in {"s", "sim", "y", "yes"}
    print("[I] Consulta unificada: HIBP, Hunter, Kickbox e CheckLeaked, conforme configuração e seleção.")
    print("[I] O endereço será enviado às fontes ativadas com chave; consultas podem consumir créditos.")
    print("[I] Configuração: " + str(configuration_path()))
    print("[I] Hunter/Kickbox fazem verificações de entregabilidade; o programa não envia mensagens de email.")
    report = lookup_email(email, config=config, consult_checkleaked=consult_checkleaked,
                          on_progress=lambda message: print("[I] " + message, flush=True))
    print(render_email_lookup(report))
    if any(item["state"] == "not_configured" for item in report["providers"]):
        print("[I] Use configurar-apis.bat na pasta do projeto para preencher as chaves.")
    return report
