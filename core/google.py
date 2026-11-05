from core.searchGoogle import manual_search


def google():
    query = input(" Pesquisa (nome, cidade, instituição ou outro termo): ").strip()
    if query:
        manual_search(query)
    else:
        print("[!] Informe um termo de pesquisa.")
