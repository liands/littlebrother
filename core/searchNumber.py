from core.searchGoogle import manual_search
from core.searchPersonne import COUNTRY_NAMES


def searchNumber(codemonpays):
    number = input(" Telefone, com código do país: ").strip()
    if not number:
        print("[!] Informe um telefone.")
        return
    country = COUNTRY_NAMES.get(str(codemonpays).upper(), "")
    print("[I] A pesquisa pública não confirma titular, localização atual ou operadora do telefone.")
    return manual_search(" ".join(value for value in (number, country) if value),
                         label="Pesquisa pública por telefone")
