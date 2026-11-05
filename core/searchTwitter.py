from core.twitterSearchTool import twitterSearchTool
from core.searchGoogle import show_manual_url


def searchTwitter():
    username = input(" Nome de usuário no X/Twitter: ").strip()
    if not username:
        print("[!] Informe um nome de usuário.")
        return
    tool = twitterSearchTool()
    tool.getInfoProfile(username)
    if not tool.success:
        print("[!] API X/Twitter: " + (tool.error or "consulta indisponível"))
        if tool.manual_url:
            show_manual_url(tool.manual_url, "Perfil público para consulta manual")
        return
    print("[+] Dados retornados pela API oficial X/Twitter:")
    fields = (
        ("Usuário", tool.username), ("ID", tool.id), ("Nome", tool.name),
        ("Localização declarada", tool.location), ("URL", tool.url),
        ("Biografia", tool.description), ("Protegido", tool.protected),
        ("Seguidores", tool.followers), ("Seguindo", tool.friends),
        ("Publicações", tool.posts), ("Criado em", tool.create),
    )
    for label, value in fields:
        if value is not None:
            print("    {0}: {1}".format(label, value))
