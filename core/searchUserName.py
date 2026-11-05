from core.searchGoogle import manual_search


def searchUserName():
    username = input(" Nome de usuário: ").strip()
    if username:
        manual_search(username, label="Pesquisa pública por nome de usuário")
    else:
        print("[!] Informe um nome de usuário.")
