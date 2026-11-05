"""Links de consulta manual; não interpreta HTML nem fabrica resultados."""
import os
import webbrowser
from urllib.parse import urlencode, urlsplit

from lib.http import validate_url


def build_search_url(query, site=None):
    query = str(query).strip()
    if not query:
        raise ValueError("Informe um termo de pesquisa.")
    if len(query) > 2000 or any(ord(char) < 32 for char in query):
        raise ValueError("O termo de pesquisa contém caracteres inválidos ou é muito longo.")
    if site:
        query = "site:" + site + " " + query
    return "https://www.google.com/search?" + urlencode({"q": query})


def show_manual_url(url, label="Consulta manual"):
    """Abre somente HTTPS e sempre imprime o link, inclusive sem navegador."""
    url = validate_url(url)
    print("[I] " + label + ": " + str(url))
    print("[I] A consulta ocorre no navegador; nenhum resultado foi coletado pelo programa.")
    if os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}:
        print("[I] Modo offline: o navegador não será aberto. O link permanece disponível para consulta posterior.")
        return str(url)
    try:
        opened = webbrowser.open(str(url), new=2)
    except (webbrowser.Error, OSError):
        opened = False
    if not opened:
        print("[I] Copie o link acima para um navegador.")
    return str(url)


def manual_search(query, site=None, label="Pesquisa manual"):
    return show_manual_url(build_search_url(query, site=site), label=label)


def manual_directory(value, domain, label):
    """Compatibilidade para os antigos wrappers de diretórios, sem ler HTML."""
    if not isinstance(value, str):
        value = getattr(value, "url", "")
    value = str(value or "").strip()
    if value.startswith("https://"):
        host = urlsplit(value).hostname
        if host and (host == domain or host.endswith("." + domain)):
            return show_manual_url(value, label=label)
        raise ValueError("O endereço não pertence ao diretório esperado.")
    if not value:
        return show_manual_url("https://www." + domain + "/", label=label)
    return manual_search(value, site=domain, label=label)


def searchGoogle(requete="", requete2=""):
    """Compatibilidade: aceita termos, não respostas HTML do scraper antigo."""
    links = []
    for query in (requete, requete2):
        if isinstance(query, str) and query.strip():
            links.append(manual_search(query))
        elif query:
            print("[I] A interpretação automática do HTML do Google foi retirada.")
    return links
