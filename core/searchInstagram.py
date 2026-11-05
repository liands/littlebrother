from core.instagramSearchTool import instagramSearchTool
from core.searchGoogle import show_manual_url


def searchInstagram():
    username = input(" Nome de usuário no Instagram: ").strip()
    if not username:
        print("[!] Informe um nome de usuário.")
        return
    tool = instagramSearchTool()
    tool.getInfo(username)
    if not tool.success:
        print("[!] API Instagram: " + (tool.error or "consulta indisponível"))
        if tool.manual_url:
            show_manual_url(tool.manual_url, "Perfil público para consulta manual")
        return
    print("[+] Dados retornados pela API oficial Instagram:")
    fields = (
        ("Usuário", tool.username), ("ID", tool.id), ("Nome", tool.name),
        ("Biografia", tool.biography), ("URL", tool.url),
        ("Seguidores", tool.followers), ("Seguindo", tool.friends),
        ("Publicações", tool.medias), ("Foto do perfil", tool.profi_pic_hd),
    )
    for label, value in fields:
        if value is not None:
            print("    {0}: {1}".format(label, value))
    print("[I] Os dados disponíveis dependem das permissões concedidas à integração Meta.")
