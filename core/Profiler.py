"""Validated profile storage, with atomic writes and a last-valid backup."""

from contextlib import contextmanager
from copy import deepcopy
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import tempfile
import threading
import time
import unicodedata

from terminaltables import SingleTable


class ProfileError(ValueError):
    """An expected storage error that the CLI can display without a traceback."""

    def __init__(self, message, code="invalid_profile"):
        super().__init__(message)
        self.code = code


_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_MAX_PROFILE_BYTES = 10 * 1024 * 1024
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
_RESERVED_NAMES.update("%s%d" % (prefix, number)
                       for prefix in ("COM", "LPT") for number in range(1, 10))


def _has_value(value):
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None and value != "" and value != [] and value != {}


def _merge_valid(previous, incoming):
    """Do not turn an absent provider field into a deletion of stored evidence."""
    merged = deepcopy(previous)
    for key, value in incoming.items():
        if not isinstance(key, str):
            raise ProfileError("As chaves do perfil devem ser texto.")
        if not _has_value(value):
            continue
        if isinstance(value, dict):
            current = merged.get(key)
            nested = _merge_valid(current if isinstance(current, dict) else {}, value)
            if nested:
                merged[key] = nested
        else:
            merged[key] = deepcopy(value)
    return merged


def _reject_constant(value):
    raise ValueError("Valor JSON não permitido: %s" % value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Chave JSON repetida.")
        result[key] = value
    return result


class Profiler:
    def __init__(self, root=None):
        self.root = Path(root).expanduser().resolve() if root is not None else None
        self.database = {}
        self.database_errors = {}
        self.count = 0
        self.size = 0
        self.last_error = None

    def _directory(self, path, create=False):
        if not path and self.root is None:
            raise ProfileError("Informe o diretório autorizado dos perfis.", "unsafe_path")
        try:
            directory = Path(path).expanduser().resolve() if path else self.root
            if self.root is not None and not directory.is_relative_to(self.root):
                raise ProfileError("O diretório está fora da pasta autorizada.", "unsafe_path")
            if create:
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not directory.is_dir():
                raise ProfileError("Diretório de perfis não encontrado.", "not_found")
            return directory
        except (OSError, RuntimeError) as exc:
            raise ProfileError("Não foi possível acessar o diretório de perfis.", "io_error") from exc

    @staticmethod
    def _name(file_name, extension):
        try:
            name = os.fspath(file_name)
        except TypeError as exc:
            raise ProfileError("Nome de arquivo inválido.", "invalid_name") from exc
        if (not isinstance(name, str) or not name or name != name.strip()
                or len(name) > 160 or re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', name)
                or PureWindowsPath(name).drive or name in (".", "..")
                or name.endswith((".", " "))):
            raise ProfileError("Nome inválido: use apenas um nome, sem caminhos ou caracteres reservados.", "invalid_name")
        name = name.replace(" ", "_")
        if not name.lower().endswith(extension):
            name += extension
        device_name = unicodedata.normalize("NFKC", name.split(".")[0]).upper()
        if device_name in _RESERVED_NAMES:
            raise ProfileError("Esse nome é reservado pelo Windows.", "invalid_name")
        return name

    @staticmethod
    def _confined(directory, name):
        target = directory / name
        try:
            if target.is_symlink() or not target.resolve().is_relative_to(directory):
                raise ProfileError("Links e caminhos fora da pasta não são permitidos.", "unsafe_path")
        except (OSError, RuntimeError) as exc:
            raise ProfileError("Caminho de arquivo inválido.", "unsafe_path") from exc
        return target

    @contextmanager
    def _locked(self, target):
        key = os.path.normcase(str(target))
        with _LOCKS_GUARD:
            lock = _LOCKS.setdefault(key, threading.RLock())
        with lock:
            lock_path = self._confined(target.parent, target.name + ".lock")
            handle = None
            acquired = False
            try:
                handle = open(lock_path, "a+b")
                try:
                    os.chmod(lock_path, 0o600)
                except OSError:
                    pass
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                deadline = time.monotonic() + 5
                while not acquired:
                    try:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except (OSError, BlockingIOError):
                        if time.monotonic() >= deadline:
                            raise ProfileError("O perfil está ocupado. Tente novamente.", "io_error")
                        time.sleep(0.05)
                yield
            finally:
                if handle is not None:
                    if acquired:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    handle.close()

    @staticmethod
    def _read(target):
        try:
            if target.stat().st_size > _MAX_PROFILE_BYTES:
                raise ProfileError("O perfil ultrapassa o limite de 10 MB.")
            with target.open("r", encoding="utf-8-sig") as handle:
                data = json.load(handle, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
            if not isinstance(data, dict):
                raise ProfileError("Perfil inválido: o JSON deve conter um objeto.")
            return data
        except FileNotFoundError as exc:
            raise ProfileError("Perfil não encontrado: %s" % target.name, "not_found") from exc
        except (UnicodeError, ValueError, RecursionError) as exc:
            if isinstance(exc, ProfileError):
                raise
            raise ProfileError("Perfil inválido: JSON ausente, corrompido ou com codificação inválida.") from exc
        except OSError as exc:
            raise ProfileError("Não foi possível ler o perfil.", "io_error") from exc

    @staticmethod
    def _atomic_write(target, text):
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=target.parent, prefix=".profile-", suffix=".tmp",
                                             delete=False) as handle:
                temp_name = handle.name
                try:
                    os.chmod(temp_name, 0o600)
                except OSError:
                    pass
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
            temp_name = None
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    def exportText(self, fileName="", path="", data=""):
        self.last_error = None
        try:
            if not isinstance(data, str):
                raise ProfileError("O relatório deve ser texto.")
            directory = self._directory(path, create=True)
            target = self._confined(directory, self._name(fileName, ".txt"))
            with self._locked(target):
                self._confined(directory, target.name)
                self._atomic_write(target, data)
            return True
        except (ProfileError, OSError, TypeError, ValueError, RecursionError) as exc:
            self.last_error = str(exc)
            return False

    def readProfile(self, fileName="", path=""):
        self.last_error = None
        try:
            directory = self._directory(path)
            target = self._confined(directory, self._name(fileName, ".prfl"))
            return self._read(target)
        except ProfileError as exc:
            self.last_error = str(exc)
            raise

    def writeProfile(self, fileName="", path="", info="", create_only=False):
        self.last_error = None
        try:
            if not isinstance(info, dict):
                raise ProfileError("Os dados do perfil devem ser um objeto JSON.")
            directory = self._directory(path, create=True)
            target = self._confined(directory, self._name(fileName, ".prfl"))
            with self._locked(target):
                self._confined(directory, target.name)
                if create_only and target.exists():
                    raise ProfileError("O perfil já existe no destino; não foi substituído.", "already_exists")
                previous = self._read(target) if target.exists() else {}
                merged = _merge_valid(previous, info)
                serialized = json.dumps(merged, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                if len(serialized.encode("utf-8")) > _MAX_PROFILE_BYTES:
                    raise ProfileError("O perfil ultrapassa o limite de 10 MB.")
                if target.exists():
                    backup = self._confined(directory, target.name + ".bak")
                    previous_text = json.dumps(previous, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                    self._atomic_write(backup, previous_text)
                self._atomic_write(target, serialized)
            return True
        except (ProfileError, OSError, TypeError, ValueError, RecursionError) as exc:
            self.last_error = str(exc)
            return False

    def importProfile(self, source_file, path=""):
        """Import the exact source filename; canonicalize only the destination.

        Source parents may differ from the private destination root because this
        method is an explicit migration operation. Existing targets are refused
        under the same process/thread lock used by regular profile writes.
        """
        self.last_error = None
        try:
            source = Path(source_file).expanduser()
            if source.suffix.casefold() != ".prfl":
                raise ProfileError("A origem deve ser um arquivo .prfl.", "invalid_name")
            destination_name = self._name(source.name, ".prfl")
            directory = source.parent.resolve()
            literal_source = self._confined(directory, source.name)
            data = self._read(literal_source)
            return self.writeProfile(destination_name, path=path, info=data, create_only=True)
        except (ProfileError, OSError, TypeError, ValueError, RecursionError) as exc:
            self.last_error = str(exc)
            return False

    def restoreProfile(self, fileName="", path=""):
        """Explicitly restore a validated .bak without overwriting that backup."""
        self.last_error = None
        try:
            directory = self._directory(path)
            target = self._confined(directory, self._name(fileName, ".prfl"))
            with self._locked(target):
                self._confined(directory, target.name)
                backup = self._confined(directory, target.name + ".bak")
                previous = self._read(backup)
                serialized = json.dumps(previous, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                self._atomic_write(target, serialized)
            return True
        except (ProfileError, OSError, TypeError, ValueError) as exc:
            self.last_error = str(exc)
            return False

    def loadDatabase(self, path):
        self.database = {}
        self.database_errors = {}
        self.count = 0
        self.size = 0
        self.last_error = None
        try:
            directory = self._directory(path, create=True)
            profiles = sorted(directory.iterdir(), key=lambda item: (item.name.casefold(), item.name))
            total_bytes = 0
            for candidate in profiles:
                if candidate.suffix.lower() != ".prfl":
                    continue
                try:
                    target = self._confined(directory, self._name(candidate.name, ".prfl"))
                    if not target.is_file():
                        continue
                    total_bytes += target.stat().st_size
                    self._read(target)
                    self.database[target.name] = len(self.database) + 1
                except (ProfileError, OSError) as exc:
                    self.database_errors[candidate.name] = str(exc)
            self.count = len(self.database)
            self.size = total_bytes / 1000
            return self.database
        except (ProfileError, OSError) as exc:
            self.last_error = str(exc)
            return self.database

    def timeSort(self, data, reverse=False):
        records = []
        for group in data:
            if not isinstance(group, dict):
                raise ProfileError("A linha do tempo deve conter objetos.", "invalid_data")
            for timestamp, value in group.items():
                try:
                    numeric = float(timestamp)
                    if isinstance(timestamp, bool) or not math.isfinite(numeric):
                        raise ValueError
                except (TypeError, ValueError) as exc:
                    raise ProfileError("Timestamp inválido na linha do tempo.", "invalid_data") from exc
                record = deepcopy(value)
                if isinstance(record, dict):
                    record.setdefault("timestamp", numeric)
                records.append((numeric, record))
        occupied = {timestamp for timestamp, _ in records}
        assigned = set()
        unique = []
        for timestamp, value in records:
            key = timestamp
            if key in assigned:
                key = math.nextafter(key, math.inf)
                while key in occupied or key in assigned:
                    key = math.nextafter(key, math.inf)
                if not math.isfinite(key):
                    raise ProfileError("Timestamp fora do intervalo permitido.", "invalid_data")
            assigned.add(key)
            unique.append((key, value))
        return dict(sorted(unique, key=lambda item: item[0], reverse=reverse))

    def showAllProfiles(self, database=""):
        profiles = database if isinstance(database, dict) else self.database
        rows = [("ID", "Nome")]
        rows.extend((str(identifier), Path(name).stem.replace("_", " "))
                    for name, identifier in profiles.items())
        print(SingleTable(rows).table)

    def searchDatabase(self, profile, database=""):
        profiles = database if isinstance(database, dict) else self.database
        query = str(profile).strip()
        if not query:
            return None
        if query.isdecimal():
            for name, identifier in profiles.items():
                if identifier == int(query):
                    return {"id": identifier, "name": Path(name).stem.replace("_", " "), "file": name}
            return None
        try:
            filename = self._name(query, ".prfl").casefold()
        except ProfileError:
            return None
        candidates = {filename}
        parts = query.replace("_", " ").split()
        if len(parts) == 2:
            candidates.add(self._name(" ".join(reversed(parts)), ".prfl").casefold())
        for name, identifier in profiles.items():
            if name.casefold() in candidates:
                return {"id": identifier, "name": Path(name).stem.replace("_", " "), "file": name}
        return None
