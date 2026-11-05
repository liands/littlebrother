"""Codificação de URLs com a biblioteca padrão; nunca repete a decodificação."""
from urllib.parse import quote, unquote


class Url:
    def __init__(self, url):
        self.url = str(url)

    def decode(self):
        return unquote(self.url, encoding="utf-8", errors="replace")

    def encode(self):
        return quote(self.url, safe=":/.%")
