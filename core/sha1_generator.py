"""Local UTF-8 SHA-1 generation for the Pwned Passwords exposure check."""
import getpass
import hashlib
import os
from pathlib import Path
import subprocess
import warnings


def sha1_text(text):
    if not isinstance(text, str):
        raise ValueError("Informe um texto para gerar o SHA-1.")
    # Preserve spaces, case and Unicode exactly; do not strip or normalize.
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest().upper()


def copy_hash(digest):
    if not isinstance(digest, str) or len(digest) != 40 or any(char not in "0123456789ABCDEFabcdef" for char in digest):
        raise ValueError("Hash SHA-1 inválido para copiar.")
    if os.name != "nt":
        print("[I] Copie manualmente a linha do hash selecionando o texto no terminal.")
        return False
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "clip.exe"
    if not executable.is_file():
        print("[!] Cópia automática indisponível. Selecione e copie a linha do hash manualmente.")
        return False
    try:
        result = subprocess.run([str(executable)], input=digest, encoding="ascii", capture_output=True,
                                shell=False, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        print("[!] Não foi possível copiar. Selecione e copie a linha do hash manualmente.")
        return False
    if result.returncode != 0:
        print("[!] Não foi possível copiar. Selecione e copie a linha do hash manualmente.")
        return False
    print("[+] Hash copiado. Use [1] SHA-1 exposure check e cole o valor.")
    return True


def generate_sha1():
    print("[I] Geração local em UTF-8. O texto/senha não é exibido, salvo ou enviado à rede.")
    print("[I] Espaços, maiúsculas e acentos são preservados. Enter vazio gera o hash de texto vazio.")
    # Refuse getpass's echoing fallback when no private terminal input is available.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            digest = sha1_text(getpass.getpass(" Texto/senha para gerar SHA-1 (entrada oculta): "))
        except getpass.GetPassWarning:
            raise ValueError("Entrada oculta indisponível. Abra pelo iniciar.bat em um terminal interativo.") from None
    print("\n[+] SHA-1 (40 caracteres; copie somente a linha abaixo):")
    print(digest)
    print("[I] Use esse valor em [1] SHA-1 exposure check.")
    while True:
        choice = input(" [c] Copiar hash / [Enter/b] Voltar: ").strip().lower()
        if choice in {"", "b", "voltar"}:
            return digest
        if choice in {"e", "exit", "sair"}:
            raise EOFError
        if choice == "c":
            copy_hash(digest)
        else:
            print("[!] Escolha c para copiar ou Enter para voltar.")
