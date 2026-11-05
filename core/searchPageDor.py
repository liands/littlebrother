"""Compatibilidade: consulta manual de diretório belga."""
from core.searchGoogle import manual_directory


def searchPageDor(requete="", num=""):
    return manual_directory(num or requete, "pagesblanches.be", "PagesBlanches: consulta manual")
