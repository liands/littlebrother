"""Optional project-root INI configuration. No environment mutation or import-time IO."""
import configparser
import os
from pathlib import Path

KEY_NAMES = ("HIBP_API_KEY", "HUNTER_API_KEY", "KICKBOX_API_KEY", "CHECKLEAKED_API_KEY")
OPTIONS = {"hibp_enabled": ("HIBP_ENABLED", "true"), "hunter_enabled": ("HUNTER_ENABLED", "true"),
           "kickbox_enabled": ("KICKBOX_ENABLED", "true"),
           "checkleaked_enabled": ("CHECKLEAKED_ENABLED", "false"),
           "hunter_max_attempts": ("HUNTER_MAX_ATTEMPTS", "2"),
           "kickbox_sandbox": ("KICKBOX_SANDBOX", "false"),
           "kickbox_timeout_ms": ("KICKBOX_TIMEOUT_MS", "6000")}


def configuration_path():
    configured = os.environ.get("LITTLEBROTHER_CONFIG")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "config.ini"


def load_email_config():
    path = configuration_path()
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    try:
        if path.exists():
            if not path.is_file() or path.stat().st_size > 65536:
                raise ValueError("Arquivo de configuração inválido ou excessivo.")
            with path.open(encoding="utf-8-sig") as stream:
                parser.read_file(stream)
    except (OSError, UnicodeError, configparser.Error):
        # ConfigParser exceptions may quote an entire line containing a secret.
        raise ValueError("Não foi possível ler a configuração. Confira o formato do arquivo com o modelo.") from None
    allowed = {"api_keys": set(KEY_NAMES), "email_lookup": set(OPTIONS)}
    if parser.defaults() or any(section not in allowed or set(parser[section]) - allowed[section] for section in parser.sections()):
        raise ValueError("Configuração contém seções/opções desconhecidas. Confira o modelo fornecido.")
    keys = {}
    for name in KEY_NAMES:
        value = os.environ.get(name, parser.get("api_keys", name, fallback=""))
        if len(value) > 8192 or not value.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Uma chave da configuração contém caracteres ou tamanho inválidos.")
        keys[name] = value.strip()
    result = {"keys": keys}
    for name, (variable, default) in OPTIONS.items():
        value = os.environ.get(variable, parser.get("email_lookup", name, fallback=default)).strip().lower()
        if name.endswith("_enabled") or name == "kickbox_sandbox":
            if value not in {"true", "false", "yes", "no", "1", "0"}:
                raise ValueError("Use true/false nas opções de ativação das consultas de email.")
            result[name] = value in {"true", "yes", "1"}
        else:
            if not value.isascii() or not value.isdigit() or len(value) > 5:
                raise ValueError("Opção numérica inválida na configuração de email.")
            number = int(value)
            minimum, maximum = (1, 2) if name == "hunter_max_attempts" else (1000, 10000)
            if not minimum <= number <= maximum:
                raise ValueError(f"{name} deve estar entre {minimum} e {maximum}.")
            result[name] = number
    return result
