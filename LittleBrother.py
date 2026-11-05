"""LittleBrother local CLI. No network activity at import or startup."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys

import settings

PACKAGES = {"requests": "requests", "terminaltables": "terminaltables", "colorama": "colorama", "exifread": "exifread", "dns": "dnspython"}
ROUTES = {
    "1": ("core.searchPersonne", "searchPersonne", True),
    "2": ("core.searchUserName", "searchUserName", False),
    "3": ("core.searchAdresse", "searchAdresse", True),
    "4": ("core.searchNumber", "searchNumber", True),
    "5": ("core.ipFinder", "ipFinder", False),
    "6": ("core.bssidFinder", "bssidFinder", False),
    "7": ("core.searchEmail", "SearchEmail", False),
    "8": ("core.mailToIP", "mailToIP", False),
    "9": ("core.employee_lookup", "employee_lookup", False),
    "10": ("core.google", "google", False),
    "11": ("core.facebookStalk", "facebookStalk", False),
    "12": ("core.searchTwitter", "searchTwitter", False),
    "13": ("core.searchInstagram", "searchInstagram", False),
    "14": ("core.exifRead", "exifRead", False),
}


def diagnostics():
    print(f"LittleBrother {settings.version} | Python {sys.version.split()[0]}")
    missing = []
    for module, package in PACKAGES.items():
        try:
            version = importlib.metadata.version(package)
            print(f"[OK] {module}: {version}")
        except importlib.metadata.PackageNotFoundError:
            missing.append(module)
            print(f"[AUSENTE] {module}")
    print(f"Perfis: {settings.data_directory()}")
    print("Inicialização local: nenhuma consulta externa necessária.")
    print("Offline:", os.environ.get("LITTLEBROTHER_OFFLINE", "0"))
    from lib.email_config import configuration_path, load_email_config
    print("Configuração de email:", configuration_path())
    try:
        email_config = load_email_config()
    except ValueError as exc:
        print("[ERRO]", exc)
        return 1
    for name, value in email_config["keys"].items():
        print(f"{name}: {'configurado' if value else 'não configurado'}")
    for name in ("X_BEARER_TOKEN", "META_ACCESS_TOKEN", "META_GRAPH_VERSION", "INSTAGRAM_USER_ID"):
        print(f"{name}: {'configurado' if os.environ.get(name) else 'não configurado'}")
    return 1 if missing else 0


def run_action(action):
    from lib.http import IntegrationError
    try:
        return action()
    except (EOFError, KeyboardInterrupt):
        raise
    except (IntegrationError, ValueError, OSError) as exc:
        print(f"[!] {exc}")
    except Exception:
        # Do not leak tracebacks containing URLs or access tokens in provider errors.
        print("[!] A operação não pôde ser concluída por um erro interno. Os dados anteriores devem ser conferidos antes de repetir.")


def navigation(choice, options, help_text):
    from lib.menu import show_screen
    if choice in {"h", "help", "ajuda"}:
        print(help_text)
        return True
    if choice in {"c", "clear", "limpar"}:
        show_screen(options)
        return True
    return False


def lookup_menu():
    from lib.menu import prompt, show_screen
    from txt.interface import LOOKUP
    from txt.help import helpLookup
    show_screen(LOOKUP)
    while True:
        choice = input(prompt("Lookup")).strip().lower()
        if navigation(choice, LOOKUP, helpLookup):
            continue
        if choice in {"b", "voltar"}:
            return
        if choice in {"e", "sair", "exit"}:
            raise EOFError
        if choice in ROUTES:
            mod, name, country = ROUTES[choice]
            def action():
                function = getattr(importlib.import_module(mod), name)
                return function(settings.codemonpays) if country else function()
            run_action(action)
        else:
            print("Escolha uma opção da lista.")


def other_menu():
    from lib.menu import prompt, show_screen
    from txt.interface import OTHER
    from txt.help import helpOtherTool
    from core.hashDecrypt import hashdecrypt
    from core.sha1_generator import generate_sha1
    show_screen(OTHER)
    while True:
        choice = input(prompt("OtherTool")).strip().lower()
        if navigation(choice, OTHER, helpOtherTool):
            continue
        if choice in {"b", "voltar"}:
            return
        if choice in {"e", "sair", "exit"}:
            raise EOFError
        if choice == "1":
            run_action(hashdecrypt)
        elif choice == "2":
            run_action(generate_sha1)
        else:
            print("Escolha uma opção da lista.")


def country_menu():
    from lib.menu import prompt, show_screen
    from txt.interface import COUNTRY, COUNTRY_CODES
    from txt.help import helpCountry
    show_screen(COUNTRY)
    while True:
        choice = input(prompt("Country")).strip().lower()
        if navigation(choice, COUNTRY, helpCountry):
            continue
        if choice in {"b", "voltar"}:
            return
        if choice in {"e", "sair", "exit"}:
            raise EOFError
        code = COUNTRY_CODES.get(choice, choice.upper())
        if code in settings.COUNTRIES:
            settings.codemonpays = code
            settings.monpays = settings.COUNTRIES[code]
            return
        print("País não reconhecido. Use uma opção da lista ou o código do país.")


def pathtrace_menu():
    from core.pathtrace import pathtrace_lookup
    from lib.menu import prompt, show_screen
    from txt.interface import TRACERT
    from txt.help import helpTracert
    show_screen(TRACERT)
    while True:
        choice = input(prompt("Tracert")).strip().lower()
        if navigation(choice, TRACERT, helpTracert):
            continue
        if choice in {"b", "voltar"}:
            return
        if choice in {"e", "sair", "exit"}:
            raise EOFError
        if choice == "1":
            run_action(pathtrace_lookup)
        else:
            print("Escolha uma opção da lista.")


def dns_menu():
    from core.dns_lookup import interactive_lookup, interactive_email_security
    from core.domain_registration import interactive_nameservers
    from lib.menu import prompt, show_screen
    from txt.interface import DNS
    from txt.help import helpDNS
    show_screen(DNS)
    while True:
        choice = input(prompt("DNS")).strip().lower()
        if navigation(choice, DNS, helpDNS):
            continue
        if choice in {"b", "voltar"}:
            return
        if choice in {"e", "sair", "exit"}:
            raise EOFError
        if choice == "1":
            run_action(interactive_lookup)
        elif choice == "2":
            run_action(interactive_email_security)
        elif choice == "3":
            run_action(interactive_nameservers)
        else:
            print("Escolha uma opção da lista.")


def subdomains_menu():
    from core.subdomains import interactive_discovery, show_sources
    from lib.menu import prompt, show_screen
    from txt.interface import SUBDOMAINS
    from txt.help import helpSubdomains
    show_screen(SUBDOMAINS)
    while True:
        choice = input(prompt("Sub-domains")).strip().lower()
        if navigation(choice, SUBDOMAINS, helpSubdomains):
            continue
        if choice in {"b", "voltar"}:
            return
        if choice in {"e", "sair", "exit"}:
            raise EOFError
        if choice == "1":
            run_action(interactive_discovery)
        elif choice == "2":
            run_action(show_sources)
        else:
            print("Escolha uma opção da lista.")


def profile_menu():
    from core.Profiler import Profiler, ProfileError
    from core.profilerFunc import profilerFunc
    from lib.menu import prompt, show_screen
    from txt.interface import PROFILER
    from txt.help import helpProfiler
    root = settings.pathDatabase
    pr = Profiler(root=root)
    show_screen(PROFILER)
    while True:
        choice = input(prompt("Profiler")).strip().lower()
        if navigation(choice, PROFILER, helpProfiler):
            continue
        if choice in {"b", "voltar"}:
            return
        if choice in {"e", "sair", "exit"}:
            raise EOFError
        def action():
            pr.loadDatabase(root)
            for filename, error in getattr(pr, "database_errors", {}).items():
                print(f"[!] Perfil ignorado: {filename}: {error}")
            if choice == "2":
                pr.showAllProfiles(pr.database)
                return
            if choice == "3":
                name = input("Nome do perfil: ").strip()
                # Never silently replace an existing profile's URLs on creation.
                if pr.searchDatabase(name, pr.database):
                    raise ValueError("Esse perfil já existe; use consultar/atualizar.")
                urls = {}
                for key in ("Twitter", "Instagram", "Facebook"):
                    value = input(f"{key} (usuário/ID autorizado ou Enter para pular): ").strip()
                    if value:
                        urls[key] = value
                if not pr.writeProfile(name, root, {"URL": urls}, create_only=True):
                    raise ValueError(getattr(pr, "last_error", None) or "Não foi possível criar o perfil.")
                print("Perfil criado.")
                return
            if choice == "5":
                name = input("Nome do perfil a restaurar (sem extensão): ").strip()
                if not pr.restoreProfile(name, root):
                    raise ValueError(getattr(pr, "last_error", None) or "Não foi possível restaurar.")
                print("Backup restaurado.")
                return
            if choice not in {"1", "4", "6"}:
                print("Escolha uma opção da lista.")
                return
            if not pr.database:
                print("Nenhum perfil válido cadastrado.")
                return
            pr.showAllProfiles(pr.database)
            selected = pr.searchDatabase(input("Nome ou ID: ").strip(), pr.database)
            if not selected:
                print("Perfil não encontrado.")
                return
            if choice == "6":
                data = pr.readProfile(selected["file"], path=root)
                section = next((key for key in data if key.casefold() == "url" and isinstance(data[key], dict)), "URL")
                existing = data.get(section, {})
                updates = {}
                for service in ("Twitter", "Instagram", "Facebook"):
                    key = next((key for key in existing if key.casefold() == service.casefold()), service)
                    current = existing.get(key, "")
                    value = input(f"{service} [atual: {current}] (Enter mantém): ").strip()
                    if value:
                        updates[key] = value
                if updates:
                    if not pr.writeProfile(selected["file"], root, {section: updates}):
                        raise ValueError(pr.last_error or "Falha ao atualizar as contas.")
                    print("Contas atualizadas; backup da versão anterior preservado.")
                else:
                    print("Nenhuma alteração informada.")
            elif choice == "1":
                profilerFunc(selected, path=root)
            else:
                data = pr.readProfile(selected["file"], path=root)
                output = selected["file"].removesuffix(".prfl") + ".txt"
                if pr.exportText(output, root, json.dumps(data, ensure_ascii=False, indent=2)):
                    print(f"Exportado: {Path(root) / output}")
                else:
                    raise ValueError(getattr(pr, "last_error", None) or "Falha ao exportar.")
        run_action(action)


def import_profiles(source):
    from core.Profiler import Profiler, ProfileError
    source = Path(source).expanduser().resolve()
    if not source.is_dir():
        raise ValueError("Informe a pasta que contém os arquivos .prfl antigos.")
    pr = Profiler(root=settings.pathDatabase)
    count = 0
    for file in sorted(source.glob("*.prfl")):
        try:
            if file.is_symlink() or file.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Arquivo ignorado: link simbólico ou tamanho excessivo.")
            if not pr.importProfile(file, settings.pathDatabase):
                print(f"[!] {file.name}: {pr.last_error or 'não importado'} Origem preservada.")
                continue
            count += 1
        except (ProfileError, ValueError, OSError):
            print(f"[!] {file.name}: arquivo inválido ou não acessível; origem preservada.")
    print(f"Perfis importados: {count}. Os originais foram preservados.")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="LittleBrother: consultas públicas e perfis locais.")
    parser.add_argument("--version", action="version", version=settings.version)
    parser.add_argument("--check", action="store_true", help="Verifica dependências/configuração sem rede e sem criar dados.")
    parser.add_argument("--offline", action="store_true", help="Desativa consultas automáticas e abertura de navegador.")
    parser.add_argument("--data-dir", help="Pasta privada alternativa para perfis.")
    parser.add_argument("--import-profiles", metavar="PASTA", help="Importa .prfl antigos sem apagar os originais.")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        parser.error("É necessário Python 3.10 ou superior.")
    if args.data_dir:
        os.environ["LITTLEBROTHER_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    if args.offline:
        os.environ["LITTLEBROTHER_OFFLINE"] = "1"
    if args.check:
        return diagnostics()
    if any(importlib.util.find_spec(module) is None for module in PACKAGES):
        print("Dependências ausentes. Execute instalar.ps1 ou use o Python do ambiente .venv.")
        return diagnostics()
    from colorama import just_fix_windows_console
    just_fix_windows_console()
    try:
        settings.init()
        if args.import_profiles:
            return import_profiles(args.import_profiles)
        from lib.menu import prompt, show_screen
        from txt.interface import MAIN
        from txt.help import helpMain
        show_screen(MAIN)
        while True:
            choice = input(prompt()).strip().lower()
            if navigation(choice, MAIN, helpMain):
                continue
            if choice in {"e", "sair", "exit", "quit"}:
                return 0
            if choice == "1":
                lookup_menu()
                show_screen(MAIN)
            elif choice == "2":
                other_menu()
                show_screen(MAIN)
            elif choice == "3":
                profile_menu()
                show_screen(MAIN)
            elif choice == "4":
                country_menu()
                show_screen(MAIN)
            elif choice == "5":
                pathtrace_menu()
                show_screen(MAIN)
            elif choice == "6":
                dns_menu()
                show_screen(MAIN)
            elif choice == "7":
                subdomains_menu()
                show_screen(MAIN)
            else:
                print("Escolha uma opção da lista.")
    except (KeyboardInterrupt, EOFError):
        print("\nEncerrado.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"[!] Não foi possível concluir: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
