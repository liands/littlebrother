"""IP geolocation over HTTPS; importing this module never makes a request."""

import ipaddress
import math

from terminaltables import SingleTable

from lib.http import IntegrationError, get_json
from lib.integrations import text_field


def lookup_ip(value):
    try:
        if not isinstance(value, str) or "%" in value:
            raise ValueError
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        raise IntegrationError("Informe um endereço IPv4 ou IPv6 válido.", code="invalid_input") from None
    if not address.is_global or address.is_multicast:
        raise IntegrationError("Endereços locais, privados ou reservados não têm geolocalização pública consultável.", code="invalid_input")
    data = get_json("https://ipwho.is/" + str(address))
    if not isinstance(data, dict) or data.get("success") is not True:
        raise IntegrationError("O serviço de IP não concluiu a consulta. Tente novamente mais tarde.", code="api_error")
    try:
        if ipaddress.ip_address(data.get("ip", "")) != address:
            raise ValueError
    except ValueError:
        raise IntegrationError("O serviço retornou um endereço IP diferente ou inválido.", code="invalid_response") from None
    connection = data.get("connection", {})
    if not isinstance(connection, dict):
        raise IntegrationError("O serviço de IP retornou dados inválidos.", code="invalid_response")
    result = {"ip": str(address), "country": text_field(data, "country"), "region": text_field(data, "region"),
              "city": text_field(data, "city"), "postal": text_field(data, "postal"),
              "isp": text_field(connection, "isp"), "org": text_field(connection, "org"),
              "latitude": None, "longitude": None}
    lat, lon = data.get("latitude"), data.get("longitude")
    if lat is not None or lon is not None:
        if (isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float))
                or not isinstance(lon, (int, float)) or not math.isfinite(lat) or not math.isfinite(lon)
                or not -90 <= lat <= 90 or not -180 <= lon <= 180):
            raise IntegrationError("O serviço de IP retornou coordenadas inválidas.", code="invalid_response")
        result.update(latitude=lat, longitude=lon)
    return result


def ipFinder():
    value = input(" Endereço IP público: ")
    try:
        data = lookup_ip(value)
    except IntegrationError as exc:
        print("[!] " + str(exc))
        return None
    rows = [("Campo", "Valor"), ("IP", data["ip"]), ("Provedor", data["isp"]),
            ("Organização", data["org"]), ("País", data["country"]),
            ("Estado / região", data["region"]), ("Cidade aproximada", data["city"]), ("CEP", data["postal"])]
    if data["latitude"] is not None:
        position = "%s,%s" % (data["latitude"], data["longitude"])
        rows.extend([("Coordenadas aproximadas", position), ("Mapa", "https://www.google.com/maps?q=" + position)])
    print("\n" + SingleTable(rows, data["ip"]).table)
    print("A geolocalização do IP é aproximada e não identifica uma pessoa ou endereço residencial.")
    return data
