"""Instagram Graph API with Facebook Login for authorized professional accounts.

Business Discovery may expose other eligible professional profiles, subject to
the application's permissions. Personal/private profile scraping is unsupported.
"""

import re
from urllib.parse import quote, urlencode

from lib.http import IntegrationError
from lib.integrations import (Adapter, count_field, graph_get, meta_config,
                              profile_identifier, required_env, text_field)


class instagramSearchTool(Adapter):
    fields = ("id", "profi_pic_hd", "biography", "username", "name", "private", "followers",
              "friends", "medias", "urlAccount", "email", "url", "adresse", "phone")
    api_fields = "id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url,website"

    def _reset(self):
        super()._reset()
        self.accounts = []
        self._authorized_profile = False

    def _handle(self, username):
        handle = profile_identifier(username, {"instagram.com", "www.instagram.com"}, r"[A-Za-z0-9_.]{1,30}")
        self.manual_url = "https://www.instagram.com/" + quote(handle, safe="") + "/"
        return handle

    def _config(self):
        base, headers = meta_config()
        identifier = required_env("INSTAGRAM_USER_ID")
        if not re.fullmatch(r"[0-9]{1,64}", identifier):
            raise IntegrationError("INSTAGRAM_USER_ID deve ser o ID numérico da conta profissional autorizada.", code="configuration")
        return base + "/" + identifier, headers

    def getInfo(self, username):
        self._reset()
        try:
            handle = self._handle(username)
            endpoint, headers = self._config()
            own = graph_get(endpoint, fields=self.api_fields, headers=headers)
            own_handle = text_field(own, "username")
            if not own_handle or not own.get("id"):
                raise IntegrationError("A API Instagram não retornou a conta profissional autorizada.", code="invalid_response")
            is_own = own_handle.casefold() == handle.casefold()
            if is_own:
                data = own
            else:
                result = graph_get(endpoint,
                                   fields="business_discovery.username(%s){%s}" % (handle, self.api_fields),
                                   headers=headers)
                data = result.get("business_discovery")
                if not isinstance(data, dict):
                    raise IntegrationError("A API Instagram não disponibilizou este perfil. Contas pessoais, privadas ou sem permissão exigem consulta manual.",
                                           code="unavailable")
            values = {"id": text_field(data, "id"), "username": text_field(data, "username"),
                      "name": text_field(data, "name"), "biography": text_field(data, "biography"),
                      "profi_pic_hd": text_field(data, "profile_picture_url"), "url": text_field(data, "website"),
                      "followers": count_field(data, "followers_count"), "friends": count_field(data, "follows_count"),
                      "medias": count_field(data, "media_count")}
            if not values["id"] or not values["username"] or values["username"].casefold() != handle.casefold():
                raise IntegrationError("A API Instagram retornou um perfil diferente ou inválido.", code="invalid_response")
            values["urlAccount"] = "https://www.instagram.com/" + quote(values["username"], safe="") + "/"
            self.__dict__.update(values)
            self._authorized_profile = is_own
            self._ok()
        except IntegrationError as exc:
            self._fail(exc)
        return self

    def searchInsta(self, nom):
        self._reset()
        self.manual_url = "https://www.instagram.com/explore/search/?" + urlencode({"q": str(nom)[:256]})
        self._fail(IntegrationError("A API Instagram não oferece busca geral de pessoas por nome. Use a busca manual.", code="unavailable"))
        return []

    def get_picturesInfo(self, url):
        try:
            handle = self._handle(url)
            if not self.success or not self.username or self.username.casefold() != handle.casefold():
                self.getInfo(handle)
            if not self.success:
                return {}
            if not self._authorized_profile:
                raise IntegrationError("O download por API é limitado à conta profissional autorizada. Consulte as publicações deste perfil manualmente.",
                                       code="unavailable")
            endpoint, headers = self._config()
            result = graph_get(endpoint + "/media", fields="id,media_type,media_url,thumbnail_url,timestamp,caption,permalink",
                               headers=headers, params={"limit": 12})
            media = result.get("data")
            if not isinstance(media, list):
                raise IntegrationError("A API Instagram retornou uma lista de publicações inválida.", code="invalid_response")
            pictures = {}
            for item in media[:12]:
                if not isinstance(item, dict):
                    raise IntegrationError("A API Instagram retornou uma publicação inválida.", code="invalid_response")
                # The existing photo download UI writes .jpg, so return photos only.
                if item.get("media_type") != "IMAGE":
                    continue
                display = text_field(item, "media_url")
                if not display:
                    continue
                pictures[len(pictures)] = {"display": display, "type_media": "Photo",
                                          "date": text_field(item, "timestamp"), "info": text_field(item, "caption") or "",
                                          "localisation": None}
            self._ok()
            return pictures
        except IntegrationError as exc:
            self._fail(exc)
            return {}

    def downloadPictures(self, url, path, filename):
        from lib.download import download
        return download(url, path, filename)

    def getMediaWithLoc(self, location):
        self._reset()
        self.manual_url = "https://www.instagram.com/explore/locations/"
        self._fail(IntegrationError("A busca de perfis por localização não está disponível nesta integração oficial. Use a navegação manual.",
                                    code="unavailable"))
        return {}

    def searchByTag(self, tag):
        self._reset()
        self.manual_url = "https://www.instagram.com/explore/tags/" + quote(str(tag).lstrip("#")[:100], safe="") + "/"
        self._fail(IntegrationError("A busca de pessoas por hashtag não está disponível nesta integração oficial. Use a navegação manual.",
                                    code="unavailable"))
        return {}
