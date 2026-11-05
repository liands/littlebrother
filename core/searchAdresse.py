from core.searchGoogle import manual_search
from core.searchPersonne import COUNTRY_NAMES


def searchAdresse(codemonpays):
    address = input(" Endereço: ").strip()
    if not address:
        print("[!] Informe um endereço.")
        return
    country = COUNTRY_NAMES.get(str(codemonpays).upper(), "")
    return manual_search(" ".join(value for value in (address, country) if value),
                         label="Pesquisa pública por endereço")
