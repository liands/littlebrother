"""Recurso legado retirado: números públicos não são um canal de autenticação."""
class receiveSms:
    def __init__(self):
        self.server_list = []
        self.url_of_site = None
        self.contentMessages = []
        self.messageText = None
        self.fromUser = None
        self.count = 0
        self.success = False
        self.status = "unavailable"
        self.error = ("Recepção de SMS em números públicos foi retirada. "
                      "Use um número sob seu controle e a integração oficial do seu provedor.")

    def searchServer(self):
        print("[I] " + self.error)
        return []

    def sms(self, url):
        print("[I] " + self.error)
        return []
