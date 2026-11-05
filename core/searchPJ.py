"""Compatibilidade: o parser HTML legado do PagesJaunes foi retirado."""
from core.searchGoogle import manual_directory


def searchPJ(requete="", num=""):
    return manual_directory(num or requete, "pagesjaunes.fr", "PagesJaunes: consulta manual")
