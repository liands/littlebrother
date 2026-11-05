"""Local numbering-plan metadata; no owner, carrier or live-location claims."""

import re

from lib.http import IntegrationError
from lib.integrations import Adapter


_BRAZIL_DDD = {
    "SP": "11 12 13 14 15 16 17 18 19", "RJ": "21 22 24", "ES": "27 28",
    "MG": "31 32 33 34 35 37 38", "PR": "41 42 43 44 45 46", "SC": "47 48 49",
    "RS": "51 53 54 55", "DF/GO": "61", "GO": "62 64", "TO": "63", "MT": "65 66",
    "MS": "67", "AC": "68", "RO": "69", "BA": "71 73 74 75 77", "SE": "79",
    "PE": "81 87", "AL": "82", "PB": "83", "RN": "84", "CE": "85 88",
    "PI": "86 89", "PA": "91 93 94", "AM": "92 97", "RR": "95", "AP": "96", "MA": "98 99",
}
_DDD_STATES = {ddd: state for state, codes in _BRAZIL_DDD.items() for ddd in codes.split()}


class searchInfoNumero(Adapter):
    fields = ("phone_type", "location", "city", "operator", "country", "e164", "source")

    def search(self, num, country="BR"):
        self._reset()
        try:
            if (not isinstance(country, str) or not isinstance(num, str) or len(num) > 64
                    or not re.fullmatch(r"\+?[0-9 ().\-]+", num.strip())):
                raise IntegrationError("Informe um número válido com DDD e código do país quando necessário.", code="invalid_input")
            cleaned = re.sub(r"[ ().\-]", "", num.strip())
            if cleaned.startswith("+33") or country.upper() == "FR" and not cleaned.startswith("+"):
                national = cleaned[3:] if cleaned.startswith("+33") else cleaned[1:] if cleaned.startswith("0") else cleaned
                if not re.fullmatch(r"[1-9][0-9]{8}", national):
                    raise IntegrationError("Número francês inválido.", code="invalid_input")
                self.country, self.e164 = "FR", "+33" + national
                self.phone_type = "Móvel (padrão de numeração)" if national[0] in "67" else "Número não móvel (padrão de numeração)"
                self.source = "Validação local de formato; operador, titular e localização atual não são determinados."
            else:
                if cleaned.startswith("+55"):
                    national = cleaned[3:]
                elif cleaned.startswith("+") or country.upper() != "BR":
                    raise IntegrationError("Metadados locais disponíveis para Brasil (+55) e França (+33). Use formato internacional.",
                                           code="unavailable")
                else:
                    national = cleaned[2:] if len(cleaned) in {12, 13} and cleaned.startswith("55") else cleaned
                if len(national) not in {10, 11} or national[:2] not in _DDD_STATES:
                    raise IntegrationError("Número brasileiro inválido: informe DDD e 8 ou 9 dígitos.", code="invalid_input")
                subscriber = national[2:]
                if not ((len(subscriber) == 9 and subscriber[0] == "9") or (len(subscriber) == 8 and subscriber[0] in "2345")):
                    raise IntegrationError("Número brasileiro não corresponde ao formato de telefone fixo ou celular.", code="invalid_input")
                self.country, self.e164 = "BR", "+55" + national
                self.phone_type = "Móvel (padrão de numeração)" if len(subscriber) == 9 else "Fixo (padrão de numeração)"
                self.location = _DDD_STATES[national[:2]] + " (área do DDD; não é a localização atual)"
                self.source = "Plano de numeração local; portabilidade impede inferir o operador. Titular não é consultado."
            self._ok()
        except IntegrationError as exc:
            self._fail(exc)
        return self
