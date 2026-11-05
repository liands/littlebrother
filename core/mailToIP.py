"""Lê cabeçalhos de email localmente e consulta somente os IPs públicos encontrados."""
import ipaddress
import re
from email import policy
from email.parser import BytesHeaderParser
from pathlib import Path

from core.RegexTool import RegexTool
from lib.http import IntegrationError, get_json

MAX_HEADER_BYTES = 2 * 1024 * 1024


def extract_received_ips(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    message = BytesHeaderParser(policy=policy.default).parsebytes(data)
    addresses = []
    for header in message.get_all("Received", []):
        indicators = RegexTool(re.sub(r"IPv6:", "", str(header), flags=re.IGNORECASE))
        for value in indicators.AddressIpv4() + indicators.AddressIpv6():
            if value not in addresses:
                addresses.append(value)
    return addresses


def _display(value):
    return "".join(char if ord(char) >= 32 and ord(char) != 127 else " " for char in str(value))


def mailToIP():
    source = Path(input(" Caminho do arquivo .eml ou de cabeçalhos: ").strip()).expanduser()
    if not source.is_file():
        print("[!] Arquivo não encontrado.")
        return
    with source.open("rb") as handle:
        data = handle.read(MAX_HEADER_BYTES + 1)
    if len(data) > MAX_HEADER_BYTES:
        print("[!] O arquivo excede o limite de 2 MB. Exporte somente os cabeçalhos.")
        return
    addresses = extract_received_ips(data)
    if not addresses:
        print("[I] Nenhum IP válido encontrado nos cabeçalhos Received.")
        return
    print("[I] Somente os IPs públicos serão enviados à API HTTPS ipwho.is.")
    print("[I] Os saltos podem ser servidores de email. Cabeçalhos e localização não comprovam a origem do remetente.")
    queried = 0
    for address in addresses:
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
        if not parsed.is_global:
            print("[I] IP local/reservado omitido da consulta: " + address)
            continue
        if queried >= 20:
            print("[I] Limite de 20 IPs por arquivo atingido.")
            break
        queried += 1
        try:
            result = get_json("https://ipwho.is/" + str(parsed))
            if not isinstance(result, dict) or result.get("success") is not True:
                print("[!] Geolocalização indisponível para " + address)
                continue
            connection = result.get("connection") or {}
            if not isinstance(connection, dict):
                connection = {}
            place = ", ".join(str(result.get(key) or "") for key in ("city", "region", "country"))
            print("[+] IP: " + address)
            print("    Provedor: " + _display(connection.get("isp") or "não informado"))
            print("    Localização aproximada: " + _display(place))
        except IntegrationError as error:
            print("[!] " + str(error))
