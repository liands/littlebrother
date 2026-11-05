"""Offline regression tests for profile safety and failed provider refreshes."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core.Profiler import Profiler, ProfileError
from core.profilerFunc import profile_report, refresh_profile
from core.watcher import watcher


PROJECT = Path(__file__).resolve().parents[1]


class ProfileStorageTests(unittest.TestCase):
    def setUp(self):
        work = PROJECT / ".work"
        work.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="profiles-test-", dir=work)
        self.directory = Path(self.temporary.name)
        self.storage = Profiler(root=self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def test_utf8_roundtrip_and_paths_with_trailing_separators(self):
        data = {"Instagram": {"name": "João França", "description": "Café ☕"}}
        self.assertTrue(self.storage.writeProfile("João França", info=data))
        for directory in (str(self.directory), str(self.directory) + "/", str(self.directory) + os.sep):
            with self.subTest(path=directory):
                self.assertEqual(self.storage.readProfile("João_França.prfl", path=directory), data)
        text = (self.directory / "João_França.prfl").read_text(encoding="utf-8")
        self.assertIn("João França", text)
        self.assertNotIn("\\u00", text)

    def test_missing_and_invalid_profiles_have_distinct_treatable_errors(self):
        with self.assertRaises(ProfileError) as missing:
            self.storage.readProfile("missing")
        self.assertEqual(missing.exception.code, "not_found")
        for payload in ("", "{broken", "[]", "null", '{"a":NaN}', '{"a":1,"a":2}', "[" * 1100):
            (self.directory / "bad.prfl").write_text(payload, encoding="utf-8")
            with self.subTest(payload=payload[:25]):
                with self.assertRaises(ProfileError) as invalid:
                    self.storage.readProfile("bad")
                self.assertEqual(invalid.exception.code, "invalid_profile")

    def test_rejects_escape_names_and_windows_devices_for_read_write_and_export(self):
        names = ("../escape", "..\\escape", "C:\\escape", "C:escape", "/escape", "\\\\host\\share",
                 "CON", "con.prfl", "aux.txt", "NUL", "PRN", "LPT1", "COM9", "COM¹", "CONIN$",
                 "", ".", "..", "...", "leading ", " leading", "trailing.", "x:y", "x|y", "a\0b")
        for name in names:
            with self.subTest(name=repr(name)):
                self.assertFalse(self.storage.writeProfile(name, info={"name": "test"}))
                self.assertTrue(self.storage.last_error)
                self.assertFalse(self.storage.exportText(name, data="report"))
                with self.assertRaises(ProfileError):
                    self.storage.readProfile(name)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_optional_root_confines_all_directory_arguments(self):
        outside = self.directory.parent / (self.directory.name + "-escape")
        self.assertFalse(self.storage.writeProfile("test", path=outside, info={"name": "test"}))
        self.assertFalse(self.storage.exportText("test", path=outside, data="report"))
        self.assertFalse(outside.exists())
        self.assertEqual(self.storage.loadDatabase(outside), {})
        with self.assertRaises(ProfileError) as error:
            self.storage.readProfile("test", path=outside)
        self.assertEqual(error.exception.code, "unsafe_path")

    def test_no_implicit_write_directory(self):
        storage = Profiler()
        self.assertFalse(storage.writeProfile("test", info={"name": "test"}))
        self.assertIn("diretório", storage.last_error)

    def test_symlink_profile_is_rejected(self):
        target = self.directory / "actual.json"
        target.write_text('{"name":"real"}', encoding="utf-8")
        link = self.directory / "link.prfl"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Este Windows não permite criar symlinks para o teste.")
        self.assertFalse(self.storage.writeProfile("link", info={"name": "changed"}))
        with self.assertRaises(ProfileError):
            self.storage.readProfile("link")
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"name": "real"})

    def test_merge_preserves_existing_fields_when_updates_are_absent(self):
        previous = {"Twitter": {"name": "Nome", "description": "Biografia", "location": "Brasil",
                                "links": ["https://example.org"], "count": 3, "verified": True}, "label": "salvo"}
        self.assertTrue(self.storage.writeProfile("safe", info=previous))
        self.assertTrue(self.storage.writeProfile("safe", info={
            "Twitter": {"name": None, "description": "", "location": "  ", "links": [],
                        "count": 0, "verified": False}, "label": {"empty": None}}))
        expected = deepcopy(previous)
        expected["Twitter"].update(count=0, verified=False)
        self.assertEqual(self.storage.readProfile("safe"), expected)

    def test_atomic_write_retains_last_valid_backup_and_refuses_corrupt_input(self):
        first = {"name": "Antigo"}
        self.assertTrue(self.storage.writeProfile("safe", info=first))
        self.assertTrue(self.storage.writeProfile("safe", info={"name": "Novo"}))
        backup = self.directory / "safe.prfl.bak"
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), first)
        backup_bytes = backup.read_bytes()
        profile = self.directory / "safe.prfl"
        profile.write_text("corrupted", encoding="utf-8")
        self.assertFalse(self.storage.writeProfile("safe", info={"name": "Destruição"}))
        self.assertEqual(profile.read_text(encoding="utf-8"), "corrupted")
        self.assertEqual(backup.read_bytes(), backup_bytes)

    def test_create_only_refuses_existing_profile_without_changing_profile_or_backup(self):
        self.assertTrue(self.storage.writeProfile("safe", info={"name": "Antigo"}))
        original = (self.directory / "safe.prfl").read_bytes()
        self.assertFalse(self.storage.writeProfile("safe", info={"name": "Novo"}, create_only=True))
        self.assertEqual((self.directory / "safe.prfl").read_bytes(), original)
        self.assertFalse((self.directory / "safe.prfl.bak").exists())

    def test_concurrent_create_only_allows_exactly_one_writer(self):
        def create(index):
            return Profiler(root=self.directory).writeProfile("unique", info={"winner": index}, create_only=True)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(create, range(12)))
        self.assertEqual(sum(results), 1)
        self.assertIn(self.storage.readProfile("unique")["winner"], range(12))
        self.assertFalse((self.directory / "unique.prfl.bak").exists())

    def test_import_reads_exact_spaced_filename_and_normalizes_destination_only(self):
        source_folder = self.directory / "old"
        source_folder.mkdir()
        destination = self.directory / "private"
        storage = Profiler(root=destination)
        source = source_folder / "Ana Silva.prfl"
        original = '{"name":"Ana com espaço"}'
        source.write_text(original, encoding="utf-8")
        self.assertTrue(storage.importProfile(source), storage.last_error)
        self.assertEqual(storage.readProfile("Ana_Silva"), {"name": "Ana com espaço"})
        self.assertEqual(source.read_text(encoding="utf-8"), original)
        self.assertFalse((destination / "Ana Silva.prfl").exists())

    def test_import_canonical_collisions_never_replace_existing_destination(self):
        source_folder = self.directory / "old"
        source_folder.mkdir()
        destination = self.directory / "private"
        storage = Profiler(root=destination)
        spaced = source_folder / "Ana Silva.prfl"
        underscored = source_folder / "Ana_Silva.prfl"
        spaced.write_text('{"name":"Perfil um"}', encoding="utf-8")
        underscored.write_text('{"name":"Perfil dois"}', encoding="utf-8")
        self.assertTrue(storage.importProfile(spaced), storage.last_error)
        original = (destination / "Ana_Silva.prfl").read_bytes()
        self.assertFalse(storage.importProfile(underscored))
        self.assertIn("já existe", storage.last_error)
        self.assertEqual((destination / "Ana_Silva.prfl").read_bytes(), original)
        self.assertEqual(storage.readProfile("Ana_Silva"), {"name": "Perfil um"})
        self.assertFalse((destination / "Ana_Silva.prfl.bak").exists())
        self.assertTrue(spaced.exists())
        self.assertTrue(underscored.exists())

    def test_import_rejects_non_profiles_and_corrupt_json_without_changing_destination(self):
        source_folder = self.directory / "old"
        source_folder.mkdir()
        for name, content in (("bad.prfl", "corrupted"), ("other.json", '{}')):
            source = source_folder / name
            source.write_text(content, encoding="utf-8")
            self.assertFalse(self.storage.importProfile(source))
        self.assertFalse(self.storage.importProfile(source_folder / "missing.prfl"))
        self.assertEqual(list(self.directory.glob("*.prfl")), [])

    def test_explicit_backup_restore_validates_and_does_not_overwrite_backup(self):
        self.assertTrue(self.storage.writeProfile("safe", info={"name": "Antigo"}))
        self.assertTrue(self.storage.writeProfile("safe", info={"name": "Novo"}))
        backup = self.directory / "safe.prfl.bak"
        backup_bytes = backup.read_bytes()
        (self.directory / "safe.prfl").write_text("corrupted", encoding="utf-8")
        self.assertTrue(self.storage.restoreProfile("safe"))
        self.assertEqual(self.storage.readProfile("safe"), {"name": "Antigo"})
        self.assertEqual(backup.read_bytes(), backup_bytes)
        backup.write_text("invalid", encoding="utf-8")
        self.assertFalse(self.storage.restoreProfile("safe"))
        self.assertEqual(self.storage.readProfile("safe"), {"name": "Antigo"})

    def test_restore_missing_backup_and_escape_are_safe(self):
        self.assertFalse(self.storage.restoreProfile("missing"))
        self.assertFalse(self.storage.restoreProfile("../escape"))

    def test_failed_replace_preserves_profile_and_cleans_temporary_file(self):
        self.assertTrue(self.storage.writeProfile("safe", info={"name": "Antigo"}))
        target = self.directory / "safe.prfl"
        original = target.read_bytes()
        real_replace = os.replace

        def fail_profile_replace(source, destination):
            if Path(destination) == target:
                raise PermissionError("simulated replace failure")
            return real_replace(source, destination)

        with patch("core.Profiler.os.replace", side_effect=fail_profile_replace):
            self.assertFalse(self.storage.writeProfile("safe", info={"name": "Novo"}))
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(json.loads((self.directory / "safe.prfl.bak").read_text(encoding="utf-8")), {"name": "Antigo"})
        self.assertEqual(list(self.directory.glob(".profile-*.tmp")), [])

    def test_first_write_and_backup_failure_leave_existing_data_intact(self):
        with patch("core.Profiler.os.replace", side_effect=PermissionError("simulated")):
            self.assertFalse(self.storage.writeProfile("new", info={"name": "Novo"}))
        self.assertFalse((self.directory / "new.prfl").exists())
        self.assertTrue(self.storage.writeProfile("safe", info={"name": "Antigo"}))
        original = (self.directory / "safe.prfl").read_bytes()
        with patch("core.Profiler.os.replace", side_effect=PermissionError("simulated")):
            self.assertFalse(self.storage.writeProfile("safe", info={"name": "Novo"}))
        self.assertEqual((self.directory / "safe.prfl").read_bytes(), original)
        self.assertEqual(list(self.directory.glob(".profile-*.tmp")), [])

    def test_non_json_update_does_not_touch_existing_profile(self):
        self.assertTrue(self.storage.writeProfile("safe", info={"name": "Antigo"}))
        original = (self.directory / "safe.prfl").read_bytes()
        for update in ({"bad": math.nan}, {"bad": object()}, [1], {1: "bad"}):
            with self.subTest(update=repr(update)):
                self.assertFalse(self.storage.writeProfile("safe", info=update))
                self.assertEqual((self.directory / "safe.prfl").read_bytes(), original)

    def test_database_is_sorted_and_reports_invalid_profiles_and_actual_size(self):
        for name in ("Zoe", "Ana", "bob"):
            self.assertTrue(self.storage.writeProfile(name, info={"name": name}))
        (self.directory / "bad.prfl").write_text("invalid", encoding="utf-8")
        (self.directory / "ignore.ini").write_text("ignore", encoding="utf-8")
        (self.directory / "Ana.prfl.bak").write_text("ignored", encoding="utf-8")
        (self.directory / "directory.prfl").mkdir()
        expected = {"Ana.prfl": 1, "bob.prfl": 2, "Zoe.prfl": 3}
        self.assertEqual(self.storage.loadDatabase(self.directory), expected)
        self.assertEqual(self.storage.loadDatabase(str(self.directory) + "/"), expected)
        self.assertEqual(self.storage.count, 3)
        self.assertEqual(set(self.storage.database_errors), {"bad.prfl"})
        size = sum(item.stat().st_size for item in self.directory.glob("*.prfl") if item.is_file())
        self.assertEqual(self.storage.size, size / 1000)

    def test_database_missing_path_can_be_created_under_root(self):
        nested = self.directory / "new"
        self.assertEqual(self.storage.loadDatabase(nested), {})
        self.assertTrue(nested.is_dir())
        self.assertIsNone(self.storage.last_error)

    def test_search_handles_empty_database_unknown_ids_case_and_reversed_name(self):
        self.assertIsNone(self.storage.searchDatabase("9", database={}))
        self.assertIsNone(self.storage.searchDatabase("../escape", database={}))
        database = {"João_Silva.prfl": 1}
        for query in ("1", "joão silva", "João_Silva.prfl", "Silva João"):
            with self.subTest(query=query):
                self.assertEqual(self.storage.searchDatabase(query, database)["file"], "João_Silva.prfl")
        self.assertIsNone(self.storage.searchDatabase("2", database))
        self.assertIsNone(self.storage.searchDatabase("", database))
        self.assertEqual(self.storage.searchDatabase("²", {"².prfl": 1})["file"], "².prfl")

    def test_concurrent_thread_updates_keep_all_fields(self):
        self.assertTrue(self.storage.writeProfile("concurrent", info={"seed": True}))

        def update(index):
            return Profiler(root=self.directory).writeProfile("concurrent", info={"worker_%d" % index: index})

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(update, range(20)))
        self.assertTrue(all(results))
        expected = {"seed": True, **{"worker_%d" % index: index for index in range(20)}}
        self.assertEqual(self.storage.readProfile("concurrent"), expected)

    def test_concurrent_process_updates_keep_all_fields(self):
        self.assertTrue(self.storage.writeProfile("concurrent", info={"seed": True}))
        script = ("from core.Profiler import Profiler; import sys; "
                  "p=Profiler(root=sys.argv[1]); "
                  "ok=p.writeProfile('concurrent',info={'process_'+sys.argv[2]:int(sys.argv[2])}); "
                  "sys.exit(0 if ok else 1)")
        processes = [subprocess.Popen([sys.executable, "-c", script, str(self.directory), str(index)],
                                      cwd=PROJECT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for index in range(6)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, (stdout + stderr).decode(errors="replace"))
        expected = {"seed": True, **{"process_%d" % index: index for index in range(6)}}
        self.assertEqual(self.storage.readProfile("concurrent"), expected)

    def test_atomic_text_export_is_confined_and_utf8(self):
        self.assertTrue(self.storage.exportText("Relatório", data="Informações de João"))
        self.assertEqual((self.directory / "Relatório.txt").read_text(encoding="utf-8"), "Informações de João")
        with patch("core.Profiler.os.replace", side_effect=PermissionError("simulated")):
            self.assertFalse(self.storage.exportText("Relatório", data="Novo"))
        self.assertEqual((self.directory / "Relatório.txt").read_text(encoding="utf-8"), "Informações de João")


class TimelineTests(unittest.TestCase):
    def test_collisions_are_preserved_without_mutating_input(self):
        nearby = math.nextafter(100.0, math.inf)
        data = [{100: {"id": "a"}}, {100: {"id": "b"}}, {100: {"id": "c"}},
                {nearby: {"id": "d"}}, {99: {"id": "e"}}]
        original = deepcopy(data)
        result = Profiler().timeSort(data)
        self.assertEqual(data, original)
        self.assertEqual(len(result), 5)
        self.assertEqual({entry["id"] for entry in result.values()}, {"a", "b", "c", "d", "e"})
        self.assertEqual([entry["timestamp"] for entry in result.values() if entry["id"] in {"a", "b", "c"}], [100] * 3)
        self.assertEqual(list(result), sorted(result))
        reverse = Profiler().timeSort(data, reverse=True)
        self.assertEqual(list(reverse), sorted(reverse, reverse=True))

    def test_invalid_timestamps_are_treatable(self):
        for value in ("not a timestamp", math.nan, math.inf, True):
            with self.subTest(value=value):
                with self.assertRaises(ProfileError):
                    Profiler().timeSort([{value: {"id": 1}}])

    def test_retired_timeline_scrapers_return_clear_unavailability_without_network(self):
        instance = watcher()
        with patch("requests.get", side_effect=AssertionError("network forbidden")):
            self.assertEqual(instance.twitterWatcher("https://x.com/example"), {})
            self.assertEqual(instance.tweet, {})
            self.assertEqual(instance.status, "unavailable")
            self.assertFalse(instance.success)
            self.assertTrue(instance.error)
            self.assertEqual(instance.instagramWatcher("example"), {})
            self.assertEqual(instance.medias, {})
            self.assertEqual(instance.status, "unavailable")
            self.assertTrue(instance.error)


class ProfileRefreshTests(unittest.TestCase):
    def setUp(self):
        self.previous = {"URL": {"Twitter": "https://x.com/example"},
                         "Twitter": {"name": "Salvo", "description": "Biografia importante", "location": "Brasil"}}

    @staticmethod
    def provider(factory):
        return [("Twitter", factory, "getInfoProfile", {"name": "name", "description": "description", "location": "location"})]

    def test_failed_provider_does_not_replace_any_saved_data(self):
        class Failure:
            success = False
            status = "error"
            error = "HTTP 503"
            name = description = location = None

            def getInfoProfile(self, account):
                return None

        previous = deepcopy(self.previous)
        updated, outcomes, changes = refresh_profile(self.previous, self.provider(Failure))
        self.assertEqual(updated, previous)
        self.assertEqual(self.previous, previous)
        self.assertIsNot(updated, self.previous)
        self.assertEqual(outcomes["Twitter"]["error"], "HTTP 503")
        self.assertEqual(changes, [])

    def test_broken_provider_is_treated_without_data_loss(self):
        class Broken:
            def getInfoProfile(self, account):
                raise ValueError("unexpected provider response with a secret")

        updated, outcomes, changes = refresh_profile(self.previous, self.provider(Broken))
        self.assertEqual(updated, self.previous)
        self.assertEqual(changes, [])
        self.assertEqual(outcomes["Twitter"]["status"], "error")
        self.assertNotIn("secret", outcomes["Twitter"]["error"])

    def test_successful_partial_provider_preserves_unavailable_fields(self):
        class Partial:
            success = True
            status = "ok"
            error = None
            name = "Nome atualizado"
            description = None
            location = "  "

            def getInfoProfile(self, account):
                self.account = account

        updated, outcomes, changes = refresh_profile(self.previous, self.provider(Partial))
        self.assertEqual(updated["Twitter"]["name"], "Nome atualizado")
        self.assertEqual(updated["Twitter"]["description"], "Biografia importante")
        self.assertEqual(updated["Twitter"]["location"], "Brasil")
        self.assertEqual(outcomes["Twitter"]["status"], "ok")
        self.assertEqual(changes, ["Twitter: name atualizado"])
        self.assertEqual(self.previous["Twitter"]["name"], "Salvo")

    def test_profile_without_accounts_skips_all_providers(self):
        def forbidden():
            raise AssertionError("provider called without an account")

        data = {"name": "Só local"}
        self.assertEqual(refresh_profile(data, self.provider(forbidden)), (data, {}, []))

    def test_case_insensitive_sections_do_not_create_duplicate_keys(self):
        class Success:
            success = True
            name = "Novo"

            def getInfoProfile(self, account):
                return None

        data = {"url": {"twitter": "example"}, "twitter": {"name": "Antigo"}}
        updated, _, _ = refresh_profile(data, self.provider(Success))
        self.assertNotIn("Twitter", updated)
        self.assertEqual(updated["twitter"]["name"], "Novo")

    def test_report_has_real_date_preserves_failure_context_and_strips_terminal_controls(self):
        data = deepcopy(self.previous)
        data["Twitter"]["name"] = "\x1b[31mNome\x1b[0m"
        report = profile_report({"name": "Perfil", "id": 1}, data,
                                {"Twitter": {"status": "error", "error": "HTTP 503"}})
        self.assertRegex(report, r"Gerado em: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}")
        self.assertIn("Dados anteriores preservados", report)
        self.assertIn("Biografia importante", report)
        self.assertNotIn("\x1b", report)
        self.assertNotIn("Gerado em: None", report)

    def test_interactive_refresh_with_failed_provider_does_not_write(self):
        module = importlib.import_module("core.profilerFunc")
        work = PROJECT / ".work"
        work.mkdir(exist_ok=True)

        class Failure:
            success = False
            status = "unavailable"
            error = "Sem credenciais"

            def getInfoProfile(self, account):
                return None

        with tempfile.TemporaryDirectory(prefix="refresh-test-", dir=work) as folder:
            storage = Profiler(root=folder)
            self.assertTrue(storage.writeProfile("profile", info=self.previous))
            target = Path(folder) / "profile.prfl"
            original = target.read_bytes()
            with patch.object(module, "_PROVIDERS", self.provider(Failure)), \
                    patch("builtins.input", return_value="n"), patch("builtins.print"):
                self.assertTrue(module.profilerFunc({"name": "Profile", "id": 1, "file": "profile.prfl"}, path=folder))
            self.assertEqual(target.read_bytes(), original)
            self.assertFalse(Path(str(target) + ".bak").exists())

    def test_refresh_writes_only_changed_fields(self):
        module = importlib.import_module("core.profilerFunc")
        previous = {"Twitter": {"name": "Antigo", "location": "Brasil"}, "Note": "saved"}
        updated = {"Twitter": {"name": "Novo", "location": "Brasil"}, "Note": "saved"}
        self.assertEqual(module._changes_only(previous, updated), {"Twitter": {"name": "Novo"}})


if __name__ == "__main__":
    unittest.main()
