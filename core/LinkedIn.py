"""Pesquisa manual: o LinkedIn não oferece aqui uma API de coleta de pessoas."""
from core.searchGoogle import build_search_url, show_manual_url


class searchLinkedIn:
    def __init__(self):
        self.found = 0
        self.employees = []
        self.profiles = []
        self.status = "manual"
        self.manual_url = None

    def search(self, searching, city):
        self.found = 0
        self.employees = []
        self.profiles = []
        self.manual_url = build_search_url(
            " ".join(str(value).strip() for value in (searching, city) if value),
            site="linkedin.com/in")
        show_manual_url(self.manual_url, "LinkedIn: consulta manual de perfis públicos")
        return self.manual_url
