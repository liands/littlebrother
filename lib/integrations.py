"""Shared validation and explicit outcomes for optional API integrations."""

import os
import re
from urllib.parse import parse_qs, urlsplit

from lib.http import IntegrationError, get_json


class Adapter:
    """A failed request never represents a negative search result."""

    fields = ()

    def __init__(self):
        self._reset()

    def _reset(self):
        self.success = False
        self.error = None
        self.status = "unavailable"
        self.manual_url = None
        for field in self.fields:
            setattr(self, field, None)

    def _ok(self):
        self.success = True
        self.error = None
        self.status = "ok"

    def _fail(self, exc):
        self.success = False
        self.error = str(exc)
        code = getattr(exc, "code", "error")
        self.status = ("unavailable" if code in {"configuration", "unavailable"}
                       else "not_found" if code == "not_found" else "error")


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise IntegrationError("Configure a variável %s para usar esta integração." % name,
                               code="configuration")
    if len(value) > 8192 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise IntegrationError("A variável %s contém um valor inválido." % name,
                               code="configuration")
    return value


def profile_identifier(value, hosts, pattern, *, facebook=False):
    """Extract a handle without ever treating user input as a network target."""
    if (not isinstance(value, str) or len(value) > 2048 or "\\" in value or
            any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise IntegrationError("Informe um usuário ou URL de perfil válido.", code="invalid_input")
    value = value.strip()
    if "://" in value:
        try:
            parsed = urlsplit(value)
            if (parsed.scheme not in {"http", "https"} or parsed.hostname not in hosts
                    or parsed.username or parsed.password or parsed.port):
                raise ValueError
            value = parsed.path.strip("/")
            if facebook and value == "profile.php":
                identifiers = parse_qs(parsed.query).get("id", [])
                if len(identifiers) != 1 or not re.fullmatch(r"[0-9]{1,64}", identifiers[0]):
                    raise ValueError
                value = identifiers[0]
        except (ValueError, TypeError):
            raise IntegrationError("URL de perfil inválido para esta plataforma.",
                                   code="invalid_input") from None
    else:
        value = value.lstrip("@").rstrip("/")
    if not re.fullmatch(pattern, value, flags=re.ASCII):
        raise IntegrationError("Identificador de perfil inválido.", code="invalid_input")
    return value


def text_field(data, key):
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise IntegrationError("A API retornou um campo de texto inválido.", code="invalid_response")
    if value is None:
        return None
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    return "".join(char for char in value if char in "\n\t" or
                   (ord(char) >= 32 and not 127 <= ord(char) <= 159))


def count_field(data, key):
    value = data.get(key)
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise IntegrationError("A API retornou uma contagem inválida.", code="invalid_response")
    return value


def meta_config():
    token = required_env("META_ACCESS_TOKEN")
    version = required_env("META_GRAPH_VERSION")
    if not re.fullmatch(r"v[1-9][0-9]{0,2}\.0", version):
        raise IntegrationError("META_GRAPH_VERSION deve ter formato como v26.0 e ser uma versão suportada pelo seu aplicativo Meta.",
                               code="configuration")
    return "https://graph.facebook.com/" + version, {"Authorization": "Bearer " + token}


def graph_get(url, *, fields, headers, params=None):
    query = dict(params or {})
    query["fields"] = fields
    result = get_json(url, params=query, headers=headers)
    if not isinstance(result, dict):
        raise IntegrationError("A API Meta retornou dados inválidos.", code="invalid_response")
    if "error" in result:
        raise IntegrationError("A API Meta recusou a consulta. Verifique token, permissões, conta e versão configurada.",
                               code="api_error")
    return result
