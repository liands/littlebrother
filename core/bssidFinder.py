"""Validated access to the documented public Wi-Fi geolocation API."""

import math
import re

from lib.http import IntegrationError, get_json


def lookup_bssid(value):
    if not isinstance(value, str):
        raise IntegrationError("Informe um BSSID válido (12 caracteres hexadecimais).", code="invalid_input")
    compact = value.strip().replace(":", "").replace("-", "")
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
        raise IntegrationError("Informe um BSSID válido, por exemplo 00:11:22:33:44:55.", code="invalid_input")
    first_octet = int(compact[:2], 16)
    if first_octet & 3 or compact.upper() in {"000000000000", "FFFFFFFFFFFF"}:
        raise IntegrationError("BSSID local, randomizado, multicast ou reservado não fornece um identificador global confiável para geolocalização.",
                               code="invalid_input")
    bssid = ":".join(compact[index:index + 2].upper() for index in range(0, 12, 2))
    result = get_json("https://api.mylnikov.org/geolocation/wifi",
                      params={"v": "1.1", "data": "open", "bssid": bssid})
    if not isinstance(result, dict):
        raise IntegrationError("O serviço Wi-Fi retornou dados inválidos.", code="invalid_response")
    if result.get("result") in (404, "404"):
        return None
    data = result.get("data")
    if result.get("result") not in (200, "200") or not isinstance(data, dict):
        raise IntegrationError("O serviço Wi-Fi não concluiu a consulta.", code="api_error")
    try:
        # Some historical responses use 'lan'; the documented field is 'lat'.
        raw_lat = data.get("lat", data.get("lan"))
        raw_lon = data.get("lon")
        if isinstance(raw_lat, bool) or isinstance(raw_lon, bool):
            raise ValueError
        lat, lon = float(raw_lat), float(raw_lon)
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError
        accuracy = data.get("range")
        if accuracy is not None:
            if isinstance(accuracy, bool):
                raise ValueError
            accuracy = float(accuracy)
            if not math.isfinite(accuracy) or accuracy < 0:
                raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise IntegrationError("O serviço Wi-Fi retornou coordenadas inválidas.", code="invalid_response") from None
    return {"bssid": bssid, "latitude": lat, "longitude": lon, "accuracy_m": accuracy}


def bssidFinder():
    value = input(" MAC / BSSID: ")
    try:
        data = lookup_bssid(value)
    except IntegrationError as exc:
        print("[!] " + str(exc))
        return None
    if data is None:
        print("[i] O BSSID não foi encontrado na base pública consultada.")
        return None
    position = "%s,%s" % (data["latitude"], data["longitude"])
    print("[+] Coordenadas aproximadas: " + position)
    if data["accuracy_m"] is not None:
        print("[i] Precisão informada pela base: %s metros." % data["accuracy_m"])
    print("[+] Mapa: https://www.google.com/maps?q=" + position)
    print("A base pode conter dados antigos; o resultado não comprova a localização atual do equipamento.")
    return data
