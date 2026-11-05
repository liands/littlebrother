"""Extração local de indicadores de texto, sem chamadas de rede."""
import ipaddress
import re


def _unique(values):
    return list(dict.fromkeys(values))


class RegexTool:
    def __init__(self, data):
        self.data = "" if data is None else str(data)
        self.email = []
        self.telephone = []
        self.urls = []
        self.ipv4 = []
        self.ipv6 = []

    def Email(self):
        self.email = _unique(re.findall(
            r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@"
            r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}",
            self.data))
        return self.email

    def TelephoneFr(self):
        self.telephone = _unique(re.findall(
            r"(?<![\w+])(?:0|[+]33[ .-]?|0033[ .-]?)[1-9](?:[ .-]?\d){8}(?!\d)",
            self.data))
        return self.telephone

    def Url(self):
        self.urls = _unique(url.rstrip(".,;:!?)") for url in re.findall(
            r"https?://[^\s<>\"']+", self.data))
        return self.urls

    def AddressIpv4(self):
        values = re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", self.data)
        self.ipv4 = self._valid_addresses(values, 4)
        return self.ipv4

    def AddressIpv6(self):
        values = re.findall(
            r"(?<![0-9A-Za-z:])(?:[0-9A-Fa-f]{0,4}:){2,}"
            r"[0-9A-Fa-f:.]*(?:%[A-Za-z0-9_.-]+)?", self.data)
        self.ipv6 = self._valid_addresses(values, 6)
        return self.ipv6

    @staticmethod
    def _valid_addresses(values, version):
        valid = []
        for value in values:
            try:
                parsed = ipaddress.ip_address(value)
            except ValueError:
                continue
            if parsed.version == version:
                valid.append(str(parsed))
        return _unique(valid)
