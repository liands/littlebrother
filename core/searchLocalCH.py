"""Compatibilidade: consulta manual de diretório suíço."""
from core.searchGoogle import manual_directory


def searchLocalCH(url):
    return manual_directory(url, "local.ch", "Local.ch: consulta manual")
