import contextlib
import getpass
import io
import os
import subprocess
import unittest
from unittest.mock import patch

from core.sha1_generator import copy_hash, generate_sha1, sha1_text


class SHA1GeneratorTests(unittest.TestCase):
    def test_known_vectors_and_exact_text_semantics(self):
        self.assertEqual(sha1_text('abc'), 'A9993E364706816ABA3E25717850C26C9CD0D89D')
        self.assertEqual(sha1_text(''), 'DA39A3EE5E6B4B0D3255BFEF95601890AFD80709')
        for value in (' abc', 'abc ', 'ABC', 'abc\n'):
            self.assertNotEqual(sha1_text(value), sha1_text('abc'))
        self.assertNotEqual(sha1_text('café'), sha1_text('cafe\u0301'))

    def test_hidden_input_offline_does_not_echo_or_send_plaintext(self):
        secret = 'Texto privado com espaços e ácentos '
        output = io.StringIO()
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), \
                patch('core.sha1_generator.getpass.getpass', return_value=secret), \
                patch('builtins.input', side_effect=['c', '']), patch('core.sha1_generator.copy_hash') as copy, \
                patch('requests.Session', side_effect=AssertionError('network')), contextlib.redirect_stdout(output):
            digest = generate_sha1()
        self.assertNotIn(secret, output.getvalue())
        self.assertIn(digest, output.getvalue())
        self.assertEqual(digest, sha1_text(secret))
        copy.assert_called_once_with(digest)

    @unittest.skipUnless(os.name == 'nt', 'Windows clipboard command')
    def test_clipboard_only_receives_hash_and_handles_failure(self):
        digest = sha1_text('abc')
        with patch('core.sha1_generator.Path.is_file', return_value=True), patch('core.sha1_generator.subprocess.run') as run, \
                contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode = 0
            self.assertTrue(copy_hash(digest))
            self.assertEqual(run.call_args.kwargs['input'], digest)
            self.assertFalse(run.call_args.kwargs['shell'])
            self.assertEqual(run.call_args.kwargs['timeout'], 3)
            self.assertTrue(run.call_args.args[0][0].lower().endswith('system32\\clip.exe'))
            run.side_effect = subprocess.TimeoutExpired([], 3)
            self.assertFalse(copy_hash(digest))
            with self.assertRaises(ValueError):
                copy_hash('not-a-hash')

    def test_no_echo_fallback_when_private_terminal_is_unavailable(self):
        with patch('core.sha1_generator.getpass.getpass', side_effect=getpass.GetPassWarning('echo unavailable')), \
                patch('builtins.input') as prompt, contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, 'Entrada oculta indisponível'):
            generate_sha1()
        prompt.assert_not_called()

    def test_original_other_tool_menu_option_two_generates_hash(self):
        import LittleBrother
        from txt.interface import OTHER
        output = io.StringIO()
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), \
                patch('lib.menu.show_screen'), patch('builtins.input', side_effect=['2', '', 'b']), \
                patch('core.sha1_generator.getpass.getpass', return_value='abc'), contextlib.redirect_stdout(output):
            LittleBrother.other_menu()
        self.assertIn('[1] SHA-1 exposure check\n [2] SHA-1 hash generator', OTHER)
        self.assertIn('A9993E364706816ABA3E25717850C26C9CD0D89D', output.getvalue())


if __name__ == '__main__':
    unittest.main()
