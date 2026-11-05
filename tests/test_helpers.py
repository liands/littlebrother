"""Regressões offline das consultas manuais e do tratamento de entradas."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from core.RegexTool import RegexTool
from core.getUrlGoogleSearch import getUrlGoogleSearch
from core.mailToIP import extract_received_ips, mailToIP
from core.searchEmail import SearchEmail
from core.hashDecrypt import hashdecrypt
from core.searchGoogle import build_search_url, manual_directory, manual_search, show_manual_url
from core.receiveSms import receiveSms
from core.shortCutUrl import shortCutUrl
from lib.Url import Url
from lib.download import download
from lib.http import IntegrationError


class EncodingTests(unittest.TestCase):
    def test_decode_unicode_incomplete_and_nested_percent_once(self):
        self.assertEqual(Url("Jo%C3%A3o%20Silva").decode(), "João Silva")
        self.assertEqual(Url("https://example.org/%ZZ%").decode(), "https://example.org/%ZZ%")
        self.assertEqual(Url("%252F").decode(), "%2F")
        self.assertEqual(Url("caf%C3%A9").decode(), "café")

    def test_encode_query_separators_and_unicode(self):
        self.assertEqual(Url("https://example.org/João?x=1&y=2").encode(),
                         "https://example.org/Jo%C3%A3o%3Fx%3D1%26y%3D2")

    def test_indicators_extract_complete_values_and_validate_ips(self):
        tool = RegexTool("a+tag@example.com; +33 1 23 45 67 89; 0123456789; "
                         "8.8.8.8 300.2.3.4 ::1 2001:db8::2 https://example.org/test.")
        self.assertEqual(tool.Email(), ["a+tag@example.com"])
        self.assertEqual(tool.TelephoneFr(), ["+33 1 23 45 67 89", "0123456789"])
        self.assertEqual(tool.AddressIpv4(), ["8.8.8.8"])
        self.assertEqual(tool.AddressIpv6(), ["::1", "2001:db8::2"])
        self.assertEqual(tool.Url(), ["https://example.org/test"])

    def test_no_data_is_empty_not_exception(self):
        tool = RegexTool(None)
        for method in (tool.Email, tool.TelephoneFr, tool.Url, tool.AddressIpv4, tool.AddressIpv6):
            self.assertEqual(method(), [])

    def test_legacy_html_links_are_optional_and_malformed_links_ignored(self):
        html = ('<a href="/url?q=https%3A%2F%2Fexample.org%2Fcaf%25C3%25A9&amp;sa=U">a</a>'
                '<a href="/url?q=javascript%3Aalert(1)">bad</a>'
                '<a href="http://evil.invalid/url?q=https://example.org/">bad</a>'
                '<a href="/url?q=https://[bad">bad</a>'
                '<a href="https://[bad">bad</a>')
        self.assertEqual(getUrlGoogleSearch(html), ["https://example.org/caf%C3%A9"])


class ManualSearchTests(unittest.TestCase):
    def test_query_cannot_add_parameters_and_preserves_unicode(self):
        query = 'João & cidade=Recife + "Silva"'
        url = build_search_url(query, site="linkedin.com/in")
        parts = urlsplit(url)
        self.assertEqual(parts.netloc, "www.google.com")
        self.assertEqual(parse_qs(parts.query), {"q": ["site:linkedin.com/in " + query]})

    def test_empty_and_control_characters_are_rejected(self):
        for query in ("", "   ", "test\nvalue", "\x1b[31mtest"):
            with self.subTest(query=repr(query)), self.assertRaises(ValueError):
                build_search_url(query)

    def test_manual_consultation_prints_link_when_browser_missing(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"LITTLEBROTHER_OFFLINE": "0"}), \
                patch("core.searchGoogle.webbrowser.open", return_value=False) as browser:
            with contextlib.redirect_stdout(output):
                url = manual_search("nome teste")
        browser.assert_called_once_with(url, new=2)
        self.assertIn("nenhum resultado foi coletado", output.getvalue())
        self.assertIn(url, output.getvalue())

    def test_dangerous_manual_urls_are_rejected_before_browser(self):
        with patch("core.searchGoogle.webbrowser.open") as browser:
            for url in ("file:///tmp/a", "javascript:alert(1)", "http://example.org/",
                        "https://user:pass@example.org/", "https://example.org/\nvalue",
                        "https://example.org\\@evil.invalid/", "https://example.org:8443/"):
                with self.subTest(url=url), self.assertRaises(IntegrationError):
                    show_manual_url(url)
            browser.assert_not_called()

    def test_directory_compatibility_does_not_open_unrelated_hosts(self):
        with self.assertRaises(ValueError):
            manual_directory("https://local.ch.evil.invalid/", "local.ch", "Diretório")

    def test_offline_mode_never_opens_browser(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"LITTLEBROTHER_OFFLINE": "1"}), \
                patch("core.searchGoogle.webbrowser.open") as browser, \
                contextlib.redirect_stdout(output):
            url = manual_search("João Recife")
        browser.assert_not_called()
        self.assertIn("Modo offline", output.getvalue())
        self.assertIn(url, output.getvalue())

    def test_shortener_returns_original_without_network_or_tracking(self):
        url = "https://example.org/photo?x=1&y=2"
        self.assertEqual(shortCutUrl(url), url)
        self.assertIsNone(shortCutUrl(None))
        with self.assertRaises(IntegrationError):
            shortCutUrl("http://example.org/")


class DownloadTests(unittest.TestCase):
    def test_download_is_bounded_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            with patch("lib.download.get_bytes", return_value=b"image") as fetch:
                destination = download("https://pbs.twimg.com/media/test.jpg", directory, "image.jpg")
                self.assertEqual(Path(destination).read_bytes(), b"image")
                fetch.assert_called_once_with("https://pbs.twimg.com/media/test.jpg", max_bytes=10 * 1024 * 1024)
                with self.assertRaises(FileExistsError):
                    download("https://pbs.twimg.com/media/test.jpg", directory, "image.jpg")
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(Path(destination).read_bytes(), b"image")

    def test_rejects_traversal_ads_and_windows_reserved_names(self):
        names = ("../a.jpg", "..\\a.jpg", "C:\\a.jpg", "a.jpg:payload", "CON", "nul.txt",
                 "LPT1.png", "COM².jpg", "x.", "file ", " x", "bad\x00.jpg", "x?.jpg", "con .txt")
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory, patch("lib.download.get_bytes") as fetch:
            for name in names:
                with self.subTest(name=repr(name)), self.assertRaises(ValueError):
                    download("https://pbs.twimg.com/media/test.jpg", directory, name)
            fetch.assert_not_called()

    def test_download_failure_does_not_create_partial_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            with patch("lib.download.get_bytes", side_effect=IntegrationError("Indisponível")):
                with self.assertRaises(IntegrationError):
                    download("https://pbs.twimg.com/media/test.jpg", directory, "image.jpg")
            self.assertEqual(list(Path(directory).iterdir()), [])


class DefensiveLookupTests(unittest.TestCase):
    def test_extracts_received_only_deduplicates_and_handles_ipv6(self):
        message = ("From: sender@example.org\r\n"
                   "Received: from mx ([IPv6:2001:db8::1]) by relay;\r\n"
                   "Received: from mx [8.8.8.8] by mx;\r\n"
                   "Received: from mx [8.8.8.8] by mx;\r\n\r\n"
                   "Body 1.1.1.1 and sender@example.org")
        self.assertEqual(extract_received_ips(message), ["2001:db8::1", "8.8.8.8"])

    def test_email_header_lookup_transmits_only_public_ip(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            source = Path(directory) / "mail.eml"
            source.write_text("From: private@example.org\nReceived: from x [10.0.0.1]\n"
                              "Received: from x [8.8.8.8]\n\nbody", encoding="utf-8")
            with patch("builtins.input", return_value=str(source)), \
                    patch("core.mailToIP.get_json", return_value={"success": True, "country": "US"}) as fetch, \
                    contextlib.redirect_stdout(io.StringIO()):
                mailToIP()
            fetch.assert_called_once_with("https://ipwho.is/8.8.8.8")

    def test_failed_breach_lookup_is_not_reported_as_no_exposure(self):
        output = io.StringIO()
        report = {"email": "user@example.org", "providers": [
            {"provider": "HIBP", "state": "auth_error", "message": "Consulta não concluída: credencial ausente.", "data": {}}]}
        with patch("builtins.input", return_value="user@example.org"), \
                patch("core.searchEmail.lookup_email", return_value=report), contextlib.redirect_stdout(output), \
                patch("core.searchEmail.load_email_config", return_value={"checkleaked_enabled": False, "keys": {}}), \
                patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'}):
            SearchEmail()
        self.assertIn("não concluída", output.getvalue())
        self.assertNotIn("Nenhum vazamento", output.getvalue())

    def test_hash_menu_uses_defensive_count_api(self):
        digest = "A" * 40
        output = io.StringIO()
        with patch("builtins.input", return_value=digest), \
                patch("core.hashDecrypt.leaked") as factory, contextlib.redirect_stdout(output):
            factory.return_value.check_password_hash.return_value = 5
            hashdecrypt()
        factory.return_value.check_password_hash.assert_called_once_with(digest)
        factory.return_value.hash.assert_not_called()
        self.assertIn("5 ocorrências", output.getvalue())

    def test_public_sms_feature_explicitly_unavailable(self):
        tool = receiveSms()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.searchServer(), [])
            self.assertEqual(tool.sms("https://example.org/"), [])
        self.assertFalse(tool.success)
        self.assertEqual(tool.status, "unavailable")
        self.assertEqual(tool.contentMessages, [])
        self.assertEqual(tool.count, 0)


if __name__ == "__main__":
    unittest.main()
