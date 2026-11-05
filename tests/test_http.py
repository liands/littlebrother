import os
import io
import unittest
from unittest.mock import patch

import requests

from lib import http


class FakeResponse:
    def __init__(self, body=b'{}', status=200, headers=None):
        self.body = body
        self.status_code = status
        self.headers = headers or {}
        class Raw(io.BytesIO):
            def read1(self, size, decode_content=False):
                return super().read1(size)
        self.raw = Raw(body)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, chunk_size):
        yield self.body


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"LITTLEBROTHER_OFFLINE": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.mock = patch("lib.http.requests.Session")
        self.session_class = self.mock.start()
        self.addCleanup(self.mock.stop)
        self.session = self.session_class.return_value.__enter__.return_value
        self.session.get.return_value = FakeResponse()

    def test_https_only_and_allowlist(self):
        for url in ("http://ipwho.is/8.8.8.8", "https://127.0.0.1/", "https://ipwho.is.evil.invalid/",
                    "https://user:secret@ipwho.is/", "https://ipwho.is:444/", "https://ipwho.is/\nabc"):
            with self.subTest(url=url), self.assertRaises(http.IntegrationError):
                http.get_json(url)
        self.session.get.assert_not_called()

    def test_network_options_and_json(self):
        self.session.get.return_value = FakeResponse(b'{"success":true}')
        self.assertEqual(http.get_json("https://ipwho.is/8.8.8.8"), {"success": True})
        options = self.session.get.call_args.kwargs
        self.assertEqual(options["timeout"], (5, 12))
        self.assertTrue(options["verify"])
        self.assertFalse(options["allow_redirects"])
        self.assertFalse(self.session.trust_env)

    def test_offline_blocks_network(self):
        with patch.dict(os.environ, {"LITTLEBROTHER_OFFLINE": "1"}), self.assertRaises(http.IntegrationError) as caught:
            http.get_json("https://ipwho.is/8.8.8.8")
        self.assertEqual(caught.exception.code, "offline")
        self.session.get.assert_not_called()

    def test_no_redirect_with_credentials(self):
        self.session.get.return_value = FakeResponse(status=302, headers={"Location": "https://example.invalid/"})
        with self.assertRaises(http.IntegrationError) as caught:
            http.get_json("https://api.x.com/2/users/me", headers={"Authorization": "Bearer private"})
        self.assertEqual(caught.exception.code, "redirect")
        self.assertEqual(self.session.get.call_count, 1)
        self.assertNotIn("private", str(caught.exception))

    def test_http_errors_have_codes_without_response_body(self):
        for status in (401, 403, 404, 429, 503):
            self.session.get.return_value = FakeResponse(b'private-token', status=status)
            with self.assertRaises(http.IntegrationError) as caught:
                http.get_json("https://haveibeenpwned.com/api/v3/breachedaccount/test")
            self.assertEqual(caught.exception.code, f"http_{status}")
            self.assertNotIn("private-token", str(caught.exception))

    def test_size_limit_even_without_content_length(self):
        self.session.get.return_value = FakeResponse(b'12345')
        with self.assertRaises(http.IntegrationError) as caught:
            http.get_bytes("https://pbs.twimg.com/test.jpg", max_bytes=4)
        self.assertEqual(caught.exception.code, "too_large")

    def test_advertised_size_rejected(self):
        self.session.get.return_value = FakeResponse(b'', headers={"Content-Length": "100"})
        with self.assertRaises(http.IntegrationError):
            http.get_bytes("https://pbs.twimg.com/test.jpg", max_bytes=4)

    def test_invalid_json(self):
        for body in (b'<html>login</html>', b'null', b'"string"', b'\xff'):
            self.session.get.return_value = FakeResponse(body)
            with self.assertRaises(http.IntegrationError):
                http.get_json("https://ipwho.is/8.8.8.8")

    def test_timeout_and_tls_are_redacted(self):
        for error, code in ((requests.exceptions.Timeout('secret url'), 'timeout'),
                            (requests.exceptions.SSLError('secret url'), 'tls_error'),
                            (requests.exceptions.ConnectionError('secret url'), 'network_error')):
            self.session.get.side_effect = error
            with self.assertRaises(http.IntegrationError) as caught:
                http.get_json("https://ipwho.is/8.8.8.8")
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn('secret', str(caught.exception))

    def test_media_domain_boundary(self):
        with self.assertRaises(http.IntegrationError):
            http.get_bytes('https://evilcdninstagram.com/file.jpg')
        self.session.get.assert_not_called()

    def test_slow_stream_deadline(self):
        self.session.get.return_value = FakeResponse(b'{}')
        with patch('lib.http.time.monotonic', side_effect=[0, 1, 31]), self.assertRaises(http.IntegrationError) as caught:
            http.get_json('https://ipwho.is/8.8.8.8')
        self.assertEqual(caught.exception.code, 'timeout')

    def test_unsolicited_compression_rejected(self):
        self.session.get.return_value = FakeResponse(b'compressed', headers={'Content-Encoding': 'gzip'})
        with self.assertRaises(http.IntegrationError):
            http.get_json('https://ipwho.is/8.8.8.8')


if __name__ == '__main__':
    unittest.main()
