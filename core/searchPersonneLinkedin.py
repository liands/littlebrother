from core.LinkedIn import searchLinkedIn


def searchPersonneLinkedin(nom, city):
    if not str(nom).strip():
        print("[!] Informe um nome.")
        return None
    return searchLinkedIn().search(nom, city)
