"""X API v2 adapter. No HTML scraping or anonymous private API calls."""

import re
from urllib.parse import quote, urlencode

from lib.http import IntegrationError, get_json
from lib.integrations import Adapter, count_field, profile_identifier, required_env, text_field


class twitterSearchTool(Adapter):
    fields = ("id", "name", "username", "location", "url", "description", "protected",
              "followers", "friends", "create", "geo", "verified", "posts", "langue",
              "urlAccount", "birth", "favoris")
    user_fields = "created_at,description,location,protected,public_metrics,url,verified"

    def _headers(self):
        return {"Authorization": "Bearer " + required_env("X_BEARER_TOKEN")}

    def searchTwitter(self, nom):
        self._reset()
        self.manual_url = "https://x.com/search?" + urlencode({"q": str(nom)[:256], "f": "user"})
        try:
            if not isinstance(nom, str) or not 1 <= len(nom.strip()) <= 256:
                raise IntegrationError("Informe uma busca de 1 a 256 caracteres.", code="invalid_input")
            if not re.fullmatch(r"[A-Za-z0-9_' ]{1,50}", nom.strip(), flags=re.ASCII):
                raise IntegrationError("A API X aceita nesta busca até 50 caracteres latinos sem acentos, números, espaços, apóstrofo e sublinhado. Para outros termos, use a busca manual.",
                                       code="unavailable")
            result = get_json("https://api.x.com/2/users/search",
                              params={"query": nom.strip(), "max_results": 20,
                                      "user.fields": "name,username"}, headers=self._headers())
            if not isinstance(result, dict) or result.get("errors"):
                raise IntegrationError("A API X recusou a busca; verifique permissões e plano contratado.", code="api_error")
            users = result.get("data")
            meta = result.get("meta", {})
            if users is None and isinstance(meta, dict) and meta.get("result_count") == 0:
                users = []
            if not isinstance(users, list):
                raise IntegrationError("A API X retornou uma busca inválida.", code="invalid_response")
            pairs = []
            for user in users[:20]:
                if not isinstance(user, dict) or not user.get("username") or not user.get("name"):
                    raise IntegrationError("A API X retornou um perfil inválido.", code="invalid_response")
                pairs.append((text_field(user, "username"), text_field(user, "name")))
            self._ok()
            return pairs
        except IntegrationError as exc:
            self._fail(exc)
            return []

    def getInfoProfile(self, username):
        self._reset()
        try:
            handle = profile_identifier(username, {"x.com", "www.x.com", "twitter.com", "www.twitter.com"},
                                        r"[A-Za-z0-9_]{1,15}")
            self.manual_url = "https://x.com/" + quote(handle, safe="")
            result = get_json("https://api.x.com/2/users/by/username/" + handle,
                              params={"user.fields": self.user_fields}, headers=self._headers())
            if not isinstance(result, dict):
                raise IntegrationError("A API X retornou dados inválidos.", code="invalid_response")
            errors = result.get("errors")
            if errors:
                if (isinstance(errors, list) and all(isinstance(item, dict) and
                        str(item.get("type", "")).endswith("/resource-not-found") for item in errors)):
                    raise IntegrationError("Perfil não encontrado pela API X.", code="not_found")
                raise IntegrationError("A API X recusou a consulta; verifique acesso e permissões.", code="api_error")
            user = result.get("data")
            if not isinstance(user, dict) or not user.get("id") or not user.get("username") or not user.get("name"):
                raise IntegrationError("A API X não retornou um perfil completo.", code="invalid_response")
            metrics = user.get("public_metrics", {})
            if not isinstance(metrics, dict):
                raise IntegrationError("A API X retornou contagens inválidas.", code="invalid_response")
            values = {key: text_field(user, key) for key in ("id", "name", "username", "location", "url", "description")}
            if (not re.fullmatch(r"[0-9]{1,64}", values["id"]) or
                    not re.fullmatch(r"[A-Za-z0-9_]{1,15}", values["username"]) or
                    values["username"].casefold() != handle.casefold()):
                raise IntegrationError("A API X retornou um identificador diferente ou inválido.", code="invalid_response")
            values.update(create=text_field(user, "created_at"), followers=count_field(metrics, "followers_count"),
                          friends=count_field(metrics, "following_count"),
                          posts=count_field(metrics, "tweet_count") if "tweet_count" in metrics else count_field(metrics, "post_count"),
                          protected=user.get("protected"), verified=user.get("verified"))
            for key in ("protected", "verified"):
                if values[key] is not None and not isinstance(values[key], bool):
                    raise IntegrationError("A API X retornou um campo booleano inválido.", code="invalid_response")
            values["urlAccount"] = "https://x.com/" + quote(values["username"], safe="")
            self.__dict__.update(values)
            self._ok()
        except IntegrationError as exc:
            self._fail(exc)
        return self
