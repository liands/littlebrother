"""Download limitado, com nome seguro e sem sobrescrever arquivos existentes."""
from pathlib import Path

from lib.http import get_bytes, validate_url

_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
_RESERVED_NAMES.update("COM" + str(index) for index in range(1, 10))
_RESERVED_NAMES.update("LPT" + str(index) for index in range(1, 10))
_RESERVED_NAMES.update(prefix + suffix for prefix in ("COM", "LPT") for suffix in "¹²³")


def download(url, path, filename):
    validated = validate_url(url)
    filename = str(filename)
    stem = filename.split(".", 1)[0].rstrip(" ").upper()
    if (not filename or filename in {".", ".."} or stem in _RESERVED_NAMES or
            any(char in filename for char in '/\\:<>\"|?*') or
            any(ord(char) < 32 or ord(char) == 127 for char in filename) or
            filename.strip() != filename or filename.endswith((" ", "."))):
        raise ValueError("Informe um nome de arquivo válido, sem diretórios ou nomes reservados.")
    directory = Path(path).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError("O diretório de destino não existe.")
    destination = directory / filename
    if destination.resolve().parent != directory:
        raise ValueError("O destino deve ficar dentro do diretório escolhido.")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("O arquivo de destino já existe; escolha outro nome.")
    data = get_bytes(validated, max_bytes=10 * 1024 * 1024)
    with destination.open("xb") as output:
        output.write(data)
    return str(destination)
