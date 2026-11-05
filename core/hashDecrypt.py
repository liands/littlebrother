"""Verificação defensiva de hashes SHA-1 pelo Pwned Passwords."""
from core.leaked import leaked
from lib.http import IntegrationError


def hashdecrypt():
    digest = input(" Hash SHA-1 da senha a verificar (40 caracteres hexadecimais): ").strip()
    print("[I] Consulta defensiva Pwned Passwords: somente os 5 primeiros caracteres do hash são enviados.")
    print("[I] O recurso não recupera nem imprime senhas.")
    try:
        count = leaked().check_password_hash(digest)
    except (IntegrationError, ValueError) as error:
        print("[!] Consulta não concluída: " + str(error))
        return
    if count:
        print("[!] Este hash aparece em dados conhecidos de exposição ({0} ocorrências).".format(count))
        print("[I] Substitua a senha e evite reutilizá-la.")
    else:
        print("[I] Hash ausente da resposta consultada. Isso não é garantia de senha segura.")
