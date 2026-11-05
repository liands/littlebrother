"""Pesquisa manual de fontes públicas, sem inferir vínculos entre homônimos."""
from core.searchGoogle import manual_search

COUNTRY_NAMES = {"BR": "Brasil", "FR": "France", "BE": "Belgique", "CH": "Suisse", "LU": "Luxembourg"}


def searchPersonne(codemonpays):
    name = input(" Nome completo: ").strip()
    city = input(" Cidade/estado (opcional): ").strip()
    if not name:
        print("[!] Informe um nome.")
        return
    country = COUNTRY_NAMES.get(str(codemonpays).upper(), "")
    return manual_search(" ".join(value for value in (name, city, country) if value),
                         label="Pesquisa pública de pessoa (confirme a identidade na fonte)")
