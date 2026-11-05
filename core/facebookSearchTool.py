"""Read explicitly authorized Facebook profiles with the official Graph API."""

import os
import re
from urllib.parse import quote, urlencode

from lib.http import IntegrationError
from lib.integrations import Adapter, graph_get, meta_config, profile_identifier, text_field


class facebookSearchTool(Adapter):
    fields = ("facebookId", "id", "name", "profile", "username", "job", "address", "affiliations")

    def _subject(self, profile):
        if not profile:
            profile = os.environ.get("FACEBOOK_USER_ID", "me").strip() or "me"
        subject = profile_identifier(profile, {"facebook.com", "www.facebook.com", "m.facebook.com"},
                                     r"[A-Za-z0-9.]{1,64}", facebook=True)
        self.manual_url = "https://www.facebook.com/" + quote(subject, safe="")
        if subject != "me" and not re.fullmatch(r"[0-9]{1,64}", subject):
            raise IntegrationError("A API Facebook não oferece consulta geral por nome de usuário. Informe 'me' ou um ID autorizado pelo token; consulte o perfil pelo link manual.",
                                   code="unavailable")
        return subject

    def searchFacebook(self, nom):
        self._reset()
        self.manual_url = "https://www.facebook.com/search/people/?" + urlencode({"q": str(nom)[:256]})
        self._fail(IntegrationError("A API Facebook não oferece busca geral de pessoas. Use a busca manual do Facebook.",
                                    code="unavailable"))
        return []

    def getInfoProfile(self, profile=""):
        self._reset()
        try:
            subject = self._subject(profile)
            base, headers = meta_config()
            data = graph_get(base + "/" + subject, fields="id,name", headers=headers)
            values = {"facebookId": text_field(data, "id"), "name": text_field(data, "name")}
            if not values["facebookId"] or not values["name"]:
                raise IntegrationError("A API Facebook não retornou o perfil autorizado.", code="invalid_response")
            values["id"] = values["facebookId"]
            # Graph IDs may be app-scoped. Do not claim they are public usernames.
            values["profile"] = self.manual_url if subject != "me" else None
            self.__dict__.update(values)
            self._ok()
        except IntegrationError as exc:
            self._fail(exc)
        return self

    def searchPageLiked(self, profile=""):
        """Only the authorized user's likes; requires the Meta user_likes permission."""
        self._reset()
        try:
            subject = self._subject(profile)
            base, headers = meta_config()
            data = graph_get(base + "/" + subject + "/likes", fields="id,name", headers=headers,
                             params={"limit": 25})
            pages = data.get("data")
            if not isinstance(pages, list):
                raise IntegrationError("A API Facebook retornou uma lista inválida.", code="invalid_response")
            results = []
            for page in pages[:25]:
                if not isinstance(page, dict):
                    raise IntegrationError("A API Facebook retornou uma página inválida.", code="invalid_response")
                identifier = text_field(page, "id")
                if not identifier or not re.fullmatch(r"[0-9]+", identifier):
                    raise IntegrationError("A API Facebook retornou uma página sem identificador válido.", code="invalid_response")
                results.append("https://www.facebook.com/" + identifier)
            self._ok()
            return results
        except IntegrationError as exc:
            self._fail(exc)
            return []
