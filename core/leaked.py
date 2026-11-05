"""Official HIBP v3 breach checks and privacy-preserving password checks."""

import re
from urllib.parse import quote

from lib.http import IntegrationError, get_json, get_text
from lib.integrations import Adapter, required_env, text_field


class leaked(Adapter):
    def hash(self, value):
        raise IntegrationError("Recuperação de senhas foi removida. Use check_password_hash com um hash SHA-1 para verificar exposição sem enviar o hash completo.",
                               code="unavailable")

    def check_password_hash(self, sha1):
        """Return the occurrence count; only a five-character prefix leaves this PC."""
        self._reset()
        self.manual_url = "https://haveibeenpwned.com/Passwords"
        try:
            if not isinstance(sha1, str) or not re.fullmatch(r"[0-9A-Fa-f]{40}", sha1.strip()):
                raise IntegrationError("Informe um hash SHA-1 de exatamente 40 caracteres hexadecimais.", code="invalid_input")
            digest = sha1.strip().upper()
            response = get_text("https://api.pwnedpasswords.com/range/" + digest[:5],
                                headers={"Add-Padding": "true", "User-Agent": "LittleBrother/2"})
            count = 0
            seen = set()
            for line in response.splitlines():
                if not re.fullmatch(r"[0-9A-Fa-f]{35}:[0-9]{1,20}", line):
                    raise IntegrationError("Pwned Passwords retornou uma resposta inválida; a verificação não foi concluída.",
                                           code="invalid_response")
                suffix, occurrences = line.upper().split(":", 1)
                if suffix in seen:
                    raise IntegrationError("Pwned Passwords retornou dados repetidos inválidos.", code="invalid_response")
                seen.add(suffix)
                if suffix == digest[5:]:
                    count = int(occurrences)
            if not seen:
                raise IntegrationError("Pwned Passwords retornou uma resposta vazia.", code="invalid_response")
            self._ok()
            return count
        except IntegrationError as exc:
            self._fail(exc)
            raise

    def email(self, email, *, api_key=None):
        self._reset()
        self.manual_url = "https://haveibeenpwned.com/"
        try:
            if (not isinstance(email, str) or not 3 <= len(email.strip()) <= 254 or
                    not re.fullmatch(r"[^@\s\x00-\x1f\x7f]+@[^@\s\x00-\x1f\x7f]+\.[^@\s\x00-\x1f\x7f]+", email.strip())):
                raise IntegrationError("Informe um endereço de email válido.", code="invalid_input")
            key = required_env("HIBP_API_KEY") if api_key is None else api_key
            if not re.fullmatch(r"[0-9A-Fa-f]{32}", key):
                raise IntegrationError("HIBP_API_KEY deve conter 32 caracteres hexadecimais.", code="configuration")
            try:
                result = get_json("https://haveibeenpwned.com/api/v3/breachedaccount/" + quote(email.strip(), safe=""),
                                  params={"truncateResponse": "false"},
                                  headers={"hibp-api-key": key, "User-Agent": "LittleBrother/2", "Accept": "application/json"})
            except IntegrationError as exc:
                if exc.code == "http_404":
                    self._ok()
                    self.status = "not_found"
                    return []
                raise
            if not isinstance(result, list):
                raise IntegrationError("HIBP retornou dados inválidos; a consulta não foi concluída.", code="invalid_response")
            breaches = []
            for item in result:
                if not isinstance(item, dict) or not item.get("Title") or not item.get("BreachDate") or "Domain" not in item:
                    raise IntegrationError("HIBP retornou um registro incompleto.", code="invalid_response")
                breaches.append({"Title": text_field(item, "Title"), "Domain": text_field(item, "Domain"),
                                 "Date": text_field(item, "BreachDate")})
            self._ok()
            return breaches
        except IntegrationError as exc:
            self._fail(exc)
            raise
