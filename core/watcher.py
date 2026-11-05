"""Compatibility surface for retired HTML timeline scrapers.

Reading timelines requires separate API products, permissions and quotas. No
HTML scraping or private endpoint fallback is attempted when those are absent.
"""


class watcher:
    def __init__(self):
        self.tweet = {}
        self.medias = {}
        self.success = False
        self.status = "unavailable"
        self.error = None

    def twitterWatcher(self, user):
        self.tweet = {}
        self.success = False
        self.status = "unavailable"
        self.error = ("Publicações do X indisponíveis: esta instalação não possui "
                      "integração autorizada com a API de timelines do X.")
        return self.tweet

    def instagramWatcher(self, user):
        self.medias = {}
        self.success = False
        self.status = "unavailable"
        self.error = ("Publicações do Instagram indisponíveis: é necessária uma "
                      "integração Meta autorizada com permissão para a conta.")
        return self.medias
