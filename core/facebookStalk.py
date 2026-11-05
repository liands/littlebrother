"""Consulta autorizada via API Meta; o Graph Search legado foi retirado."""
from core.facebookSearchTool import facebookSearchTool
from core.searchGoogle import show_manual_url


def facebookStalk():
    profile = input(" Identificador do perfil/página Facebook autorizado: ").strip()
    if not profile:
        print("[!] Informe um identificador.")
        return
    tool = facebookSearchTool()
    tool.getInfoProfile(profile)
    if not tool.success:
        print("[!] API Facebook: " + (tool.error or "consulta indisponível"))
        if tool.manual_url:
            show_manual_url(tool.manual_url, "Facebook para consulta manual")
        return
    print("[+] Dados retornados pela API oficial Facebook:")
    for label, value in (
        ("Nome", tool.name), ("ID", tool.facebookId),
        ("Localização declarada", tool.address), ("Trabalho declarado", tool.job),
    ):
        if value is not None:
            print("    {0}: {1}".format(label, value))
    if tool.manual_url:
        print("[I] Perfil/página: " + tool.manual_url)
