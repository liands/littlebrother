"""Local configuration. Initializing never makes network calls."""
import os
from pathlib import Path

version = "7.0.0"
COUNTRIES = {"BR": "Brasil", "FR": "França", "BE": "Bélgica", "CH": "Suíça", "LU": "Luxemburgo", "XX": "Todos"}
monip = "Não consultado"
monpays = "Brasil"
codemonpays = "BR"
pathDatabase = ""

def data_directory():
    override = os.environ.get("LITTLEBROTHER_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return (base / "LittleBrother" / "profiles").resolve()

def init(create=True):
    global pathDatabase, codemonpays, monpays
    pathDatabase = str(data_directory())
    country = os.environ.get("LITTLEBROTHER_COUNTRY", "BR").upper()
    codemonpays = country if country in COUNTRIES else "BR"
    monpays = COUNTRIES[codemonpays]
    if create:
        data_directory().mkdir(mode=0o700, parents=True, exist_ok=True)
    return pathDatabase
