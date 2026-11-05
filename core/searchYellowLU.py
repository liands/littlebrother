"""Compatibilidade: consulta manual de diretório luxemburguês."""
from core.searchGoogle import manual_directory


def searchYellowLU(url):
    return manual_directory(url, "yellow.lu", "Yellow.lu: consulta manual")
