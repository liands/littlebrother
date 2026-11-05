from core.LinkedIn import searchLinkedIn


def employee_lookup():
    company = input(" Empresa: ").strip()
    city = input(" Cidade (opcional): ").strip()
    if not company:
        print("[!] Informe o nome da empresa.")
        return
    print("[I] A pesquisa usa termos públicos; vínculo profissional precisa ser confirmado na fonte.")
    searchLinkedIn().search(company, city)
