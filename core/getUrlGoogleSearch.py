"""Compatibilidade para HTML já fornecido, sem buscar páginas no Google."""
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = unescape(dict(attrs).get("href") or "")
        try:
            parts = urlsplit(href)
        except ValueError:
            return
        if parts.path != "/url":
            return
        if parts.netloc and parts.hostname not in {"www.google.com", "www.google.fr", "google.com", "google.fr"}:
            return
        query = parse_qs(parts.query)
        target = (query.get("q") or query.get("url") or [None])[0]
        if not target:
            return
        try:
            destination = urlsplit(target)
        except ValueError:
            return
        if (destination.scheme in {"http", "https"} and destination.hostname and
                destination.username is None and destination.password is None and
                not any(ord(char) < 32 for char in target) and target not in self.urls):
            self.urls.append(target)


def getUrlGoogleSearch(content):
    parser = _LinkParser()
    parser.feed(str(content or ""))
    return parser.urls
