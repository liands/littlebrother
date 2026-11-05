import contextlib
import importlib
import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_import_does_not_initialize_or_connect(self):
        with patch('requests.Session', side_effect=AssertionError('network at import')), patch('builtins.input', side_effect=AssertionError('prompt at import')):
            for file in list((ROOT / 'core').glob('*.py')) + list((ROOT / 'lib').glob('*.py')):
                if file.stem != '__init__':
                    importlib.import_module(f'{file.parent.name}.{file.stem}')
            import LittleBrother
            with patch('settings.init', side_effect=AssertionError('startup')):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(LittleBrother.main(['--check']), 0)

    def test_cli_offline_start_exit_and_empty_database(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as data:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', data],
                                    input='3\n2\nb\ne\n', text=True, encoding='utf-8', capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertNotIn('Traceback', result.stderr + result.stdout)

    def test_cli_create_and_export_without_network(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as data:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', data],
                                    input='3\n3\nPerfil Teste\n\n\n\n4\n1\nb\ne\n', text=True, encoding='utf-8', capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((Path(data) / 'Perfil_Teste.prfl').exists(), result.stdout)
            self.assertTrue((Path(data) / 'Perfil_Teste.txt').exists(), result.stdout)

    def test_diagnostics_does_not_print_token(self):
        import LittleBrother
        with patch.dict(os.environ, {'X_BEARER_TOKEN': 'TOP-SECRET-TEST-TOKEN'}):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                LittleBrother.main(['--check'])
            self.assertNotIn('TOP-SECRET-TEST-TOKEN', output.getvalue())

    def test_import_spaces_and_collision_never_replaces_existing(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            source = Path(directory) / 'old'
            target = Path(directory) / 'private'
            source.mkdir()
            target.mkdir()
            (source / 'Ana Silva.prfl').write_text('{"name":"Imported"}', encoding='utf-8')
            command = [sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', str(target), '--import-profiles', str(source)]
            first = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=10)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            saved = target / 'Ana_Silva.prfl'
            self.assertEqual(json.loads(saved.read_text(encoding='utf-8'))['name'], 'Imported')
            (source / 'Ana_Silva.prfl').write_text('{"name":"Collision"}', encoding='utf-8')
            second = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=10)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(json.loads(saved.read_text(encoding='utf-8'))['name'], 'Imported')

    def test_edit_accounts_preserves_other_accounts(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as data:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', data],
                                    input='3\n3\nEdit Test\noldhandle\ninstagram\nme\n6\n1\nnewhandle\n\n\nb\ne\n',
                                    text=True, encoding='utf-8', capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            saved = json.loads((Path(data) / 'Edit_Test.prfl').read_text(encoding='utf-8'))
            self.assertEqual(saved['URL'], {'Twitter': 'newhandle', 'Instagram': 'instagram', 'Facebook': 'me'})
            self.assertTrue((Path(data) / 'Edit_Test.prfl.bak').exists())

    def test_original_navigation_help_clear_back_and_numbered_country(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as data:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', data],
                                    input='h\nc\n1\nh\nc\nb\n2\nh\nc\nb\n3\nh\nc\n2\nb\n4\nh\nc\n1\ne\n',
                                    text=True, encoding='utf-8', capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertNotIn('Traceback', result.stderr)
            self.assertNotIn('SyntaxWarning', result.stderr)
            for context in ('~', 'Lookup', 'OtherTool', 'Profiler', 'Country'):
                self.assertIn(f'LittleBrother({context})$', result.stdout)
            for label in ('[1] Lookup', '[2] Other tool', '[3] Profiler', '[4] Change country',
                          '[1] Profiler', '[2] Show all Profiles', '[3] Create profile',
                          'Author:    [ Lulz3xploit ]', 'Version:   [ 7.0.0 ]',
                          'Database:  [ 0 | 0.00 Ko ]'):
                self.assertIn(label, result.stdout)
            self.assertRegex(result.stdout, r'(?:País|Pays):\s+\[ França \| FR \]')

    def test_original_profiler_option_one_refreshes_profile(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as data:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', data],
                                    input='3\n3\nOriginal Menu\n\n\n\n1\n1\nn\nb\ne\n',
                                    text=True, encoding='utf-8', capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn('Nenhuma conta configurada para consulta.', result.stdout)
            self.assertTrue((Path(data) / 'Original_Menu.prfl').exists())

    def test_pathtrace_menu_help_clear_offline_lookup_and_back(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as data:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', data],
                                    input='5\nh\nc\n1\nb\ne\n', text=True, encoding='utf-8', capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn('[5] Tracert / Pathtrace', result.stdout)
            self.assertIn('[1] Lookup host', result.stdout)
            self.assertIn('LittleBrother(Tracert)$', result.stdout)
            self.assertIn('Tracert/Pathtrace não envia sondagens de rede.', result.stdout)

    def test_dns_menu_help_clear_both_offline_actions_and_back(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as data:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', data],
                                    input='6\nh\nc\n1\n2\nb\ne\n', text=True, encoding='utf-8', capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn('[6] DNS lookup', result.stdout)
            self.assertIn('[2] SPF / DKIM / DMARC', result.stdout)
            self.assertIn('LittleBrother(DNS)$', result.stdout)
            self.assertIn('nenhuma consulta DNS foi iniciada.', result.stdout)


if __name__ == '__main__':
    unittest.main()
