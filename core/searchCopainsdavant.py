"""Consulta manual, sem acessar perfis nem extrair biografias."""
from core.searchGoogle import manual_search


def searchCopainsdavant(nom, city):
    query = " ".join(str(value).strip() for value in (nom, city) if value)
    return manual_search(query, site="copainsdavant.linternaute.com",
                         label="Copains d'avant: consulta manual")
