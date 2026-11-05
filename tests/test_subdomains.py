import contextlib
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import subdomains as sd
from lib.http import IntegrationError

ROOT = Path(__file__).resolve().parents[1]


class SubdomainTests(unittest.TestCase):
    def test_domain_idna_case_and_trailing_dot(self):
        self.assertEqual(sd.validate_domain('EXAMPLE.COM.'), 'example.com')
        self.assertEqual(sd.validate_domain('bücher.de'), 'xn--bcher-kva.de')

    def test_invalid_targets_never_start_sources(self):
        with patch.object(sd, '_source') as source:
            for value in ('https://example.com', '-example.com', 'x.com;whoami', '*.example.com',
                          '127.0.0.1', '::1', 'localhost', 'x.com/abc', 'x.com:443', 'x..com',
                          'x.com\n', 'x.com|dir', 'example.123', '_srv.example.com'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    sd.discover(value)
            source.assert_not_called()

    def test_invalid_options_never_start_sources(self):
        with patch.object(sd, '_source') as source:
            for value in (True, 9, 301, 10.5, float('nan'), '30'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    sd.discover('example.com', timeout=value)
            for value in ([], ['crt.sh', 'crt.sh'], ['unknown'], 'crt.sh', [{}]):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    sd.discover('example.com', sources=value)
            source.assert_not_called()

    def test_offline_blocks_http_and_processes(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), patch.object(sd, '_source') as source:
            result = sd.discover('example.com')
            self.assertEqual(result['status'], 'offline')
            self.assertTrue(all(s['status'] == 'offline' for s in result['sources']))
            source.assert_not_called()

    def test_scope_deduplication_wildcards_and_provenance(self):
        result = sd._result('subfinder')
        for candidate in ('WWW.EXAMPLE.COM.', 'www.example.com', 'badexample.com', 'example.com.evil.org',
                          'example.com', 'https://www.example.com', '\x1b[31mwww.example.com'):
            sd._add(result, 'example.com', candidate, 'crtsh')
        sd._add(result, 'example.com', 'www.example.com', 'github')
        sd._add(result, 'example.com', '*.example.com')
        sd._add(result, 'example.com', '*.deep.example.com')
        self.assertEqual(result['names'], {'www.example.com': {'subfinder:crtsh', 'subfinder:github'}})
        self.assertEqual(set(result['wildcards']), {'*.example.com', '*.deep.example.com'})

    def test_bad_provider_cannot_inject_terminal_or_csv_content(self):
        result = sd._result('subfinder')
        sd._add(result, 'example.com', 'a.example.com', '\x1b[31msecret')
        self.assertEqual(result['names']['a.example.com'], {'subfinder'})

    def test_name_limit_keeps_existing_provenance(self):
        result = sd._result('subfinder')
        with patch.object(sd, 'MAX_NAMES', 1):
            sd._add(result, 'example.com', 'a.example.com', 'one')
            sd._add(result, 'example.com', 'b.example.com', 'two')
            sd._add(result, 'example.com', 'a.example.com', 'three')
        self.assertTrue(result['truncated'])
        self.assertEqual(result['names'], {'a.example.com': {'subfinder:one', 'subfinder:three'}})

    def test_crtsh_multiline_and_query(self):
        result = sd._result('crt.sh')
        with patch.object(sd, 'get_json', return_value=[{'name_value': 'a.example.com\n*.example.com\nforeign.org'}]) as fetch:
            sd._crtsh('example.com', result)
        self.assertEqual(fetch.call_args.kwargs['params'], {'q': '%.example.com', 'output': 'json'})
        self.assertEqual(set(result['names']), {'a.example.com'})
        self.assertEqual(set(result['wildcards']), {'*.example.com'})

    def test_crtsh_error_body_is_not_empty_success(self):
        with patch.object(sd, 'get_json', return_value={'error': 'failed'}):
            result = sd._source('crt.sh', 'example.com', 10)
        self.assertEqual(result['status'], 'error')

    def test_certspotter_pagination_and_private_auth(self):
        pages = [[{'id': '123', 'dns_names': ['a.example.com', '*.example.com']}], []]
        result = sd._result('CertSpotter')
        with patch.dict(os.environ, {'CERTSPOTTER_API_KEY': 'SECRET'}), patch.object(sd, 'get_json', side_effect=pages) as fetch:
            sd._certspotter('example.com', result)
        self.assertEqual(fetch.call_args_list[1].kwargs['params']['after'], '123')
        self.assertNotIn('after', fetch.call_args_list[0].kwargs['params'])
        self.assertEqual(fetch.call_args.kwargs['headers'], {'Authorization': 'Bearer SECRET'})
        self.assertNotIn('SECRET', repr(result))

    def test_certspotter_page_cap_marks_partial(self):
        with patch.object(sd, 'MAX_PAGES', 2), patch.object(sd, 'get_json', side_effect=[
                [{'id': '1', 'dns_names': ['a.example.com']}], [{'id': '2', 'dns_names': ['b.example.com']}] ]):
            result = sd._source('CertSpotter', 'example.com', 10)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['names']), 2)

    def test_partial_page_survives_quota_and_no_secret_in_errors(self):
        with patch.object(sd, 'get_json', side_effect=[
                [{'id': '1', 'dns_names': ['a.example.com']}], IntegrationError('URL?token=SECRET', code='http_429')]):
            result = sd._source('CertSpotter', 'example.com', 10)
        self.assertEqual(result['status'], 'partial')
        self.assertIn('a.example.com', result['names'])
        self.assertNotIn('SECRET', repr(result))
        self.assertIn('http_429', result['message'])

    def test_certspotter_repeated_cursor_is_failure(self):
        page = [{'id': '1', 'dns_names': ['a.example.com']}]
        with patch.object(sd, 'get_json', return_value=page):
            result = sd._source('CertSpotter', 'example.com', 10)
        self.assertEqual(result['status'], 'partial')
        self.assertIn('invalid_response', result['message'])

    def test_hackertarget_quota_with_200_is_failure(self):
        with patch.object(sd, 'get_text', return_value='API count exceeded - Increase Quota with Membership'):
            result = sd._source('HackerTarget', 'example.com', 10)
        self.assertEqual(result['status'], 'error')

    def test_hackertarget_free_cap_and_scope(self):
        rows = '\n'.join(f'a{i}.example.com,192.0.2.1' for i in range(50)) + '\nforeign.org,192.0.2.1'
        with patch.dict(os.environ, {'HACKERTARGET_API_KEY': ''}), patch.object(sd, 'get_text', return_value=rows):
            result = sd._source('HackerTarget', 'example.com', 10)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(result['names']), 50)

    def test_native_command_is_passive_and_json_sources_merge(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            with patch('settings.data_directory', return_value=Path(directory)), patch.object(sd, 'find_tool', return_value='C:/subfinder.exe'), \
                    patch.object(sd, '_provider_config', return_value=None), patch.object(sd, '_run_process', return_value=(
                        'ok', '{"host":"a.example.com","sources":["github","crtsh"]}\nmalformed\n', '')) as run:
                result = sd._source('subfinder', 'example.com', 90)
            command = run.call_args.args[0]
            self.assertIn('-all', command)
            self.assertIn('-duc', command)
            self.assertEqual(command[command.index('-max-time') + 1], '1')
            self.assertNotIn('-active', command)
            self.assertIn('crtsh,certspotter,hackertarget', command)
            self.assertEqual(result['names']['a.example.com'], {'subfinder:github', 'subfinder:crtsh'})
            self.assertEqual(result['status'], 'partial')

    def test_native_invalid_json_is_not_empty_success(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            with patch('settings.data_directory', return_value=Path(directory)), patch.object(sd, 'find_tool', return_value='C:/subfinder.exe'), \
                    patch.object(sd, '_provider_config', return_value=None), patch.object(sd, '_run_process', return_value=('ok', 'unexpected output\n', '')):
                result = sd._source('subfinder', 'example.com', 10)
            self.assertEqual(result['status'], 'error')

    def test_amass_without_passive_is_never_enumerated(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            with patch('settings.data_directory', return_value=Path(directory)), patch.object(sd, 'find_tool', return_value='C:/amass.exe'), \
                    patch.object(sd, '_run_process', return_value=('ok', 'Usage: enum -active', '')) as run:
                result = sd._source('amass', 'example.com', 10)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(result['status'], 'unsupported')

    def test_amass_supported_runs_only_passive(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            with patch('settings.data_directory', return_value=Path(directory)), patch.object(sd, 'find_tool', return_value='C:/amass.exe'), \
                    patch.object(sd, '_run_process', side_effect=[('error', '  -passive\n description', ''), ('ok', 'a.example.com (FQDN) --> a_record --> 192.0.2.1 (IPAddress)\n', '')]) as run:
                result = sd._source('amass', 'example.com', 10)
            self.assertIn('-passive', run.call_args.args[0])
            self.assertIn('a.example.com', result['names'])

    def test_missing_binary_is_explicit(self):
        with patch.object(sd, 'find_tool', return_value=None):
            result = sd._source('assetfinder', 'example.com', 10)
        self.assertEqual(result['status'], 'missing')

    def test_process_timeout_preserves_output_and_kills_child(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            status, output, message = sd._run_process([sys.executable, '-c',
                'import time; print("a.example.com", flush=True); time.sleep(20)'], 0.5, directory)
        self.assertEqual(status, 'partial')
        self.assertIn('a.example.com', output)
        self.assertIn('Timeout', message)

    def test_process_output_cap(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory, patch.object(sd, 'MAX_OUTPUT', 1000):
            status, output, _ = sd._run_process([sys.executable, '-c',
                'print("a.example.com\\n"*10000)'], 5, directory)
        self.assertEqual(status, 'partial')
        self.assertLessEqual(len(output), 1000)

    def test_help_capture_reads_stderr_but_normal_capture_does_not(self):
        command = [sys.executable, '-c', 'import sys; print("-passive", file=sys.stderr)']
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            self.assertIn('-passive', sd._run_process(command, 5, directory, include_stderr=True)[1])
            self.assertNotIn('-passive', sd._run_process(command, 5, directory)[1])

    def test_aggregation_preserves_each_source_status(self):
        def source(name, domain, timeout):
            result = sd._result(name)
            if name == 'assetfinder':
                result['status'] = 'missing'
            else:
                sd._add(result, domain, 'WWW.EXAMPLE.COM')
                sd._add(result, domain, '*.example.com')
            return result
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'}), patch.object(sd, '_source', side_effect=source):
            report = sd.discover('example.com')
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(len(report['hosts']), 1)
        self.assertEqual(len(report['hosts'][0]['sources']), 5)
        self.assertFalse(report['dns_verified'])
        self.assertEqual(report['hosts'][0]['dns_status'], 'not_checked')
        self.assertEqual(len(report['wildcards']), 1)

    def test_unexpected_failure_is_isolated_and_not_reported_as_no_findings(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'}), patch.object(sd, '_source', side_effect=RuntimeError('SECRET')):
            report = sd.discover('example.com')
        self.assertEqual(report['status'], 'unavailable')
        self.assertNotIn('SECRET', json.dumps(report))

    def test_exports_include_hosts_wildcards_and_failures(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}):
            report = sd.discover('example.com')
        report['hosts'] = [{'hostname': 'a.example.com', 'sources': ['crt.sh'], 'dns_status': 'not_checked'}]
        report['wildcards'] = [{'pattern': '*.example.com', 'sources': ['CertSpotter']}]
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            first = sd.export_report(report, 'json', directory=directory)
            second = sd.export_report(report, 'json', directory=directory)
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads(first.read_text(encoding='utf-8')), report)
            csv_file = sd.export_report(report, 'csv', directory=directory)
            with csv_file.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual({r['kind'] for r in rows}, {'report', 'host', 'wildcard', 'source'})
            self.assertTrue(any(r['status'] == 'offline' for r in rows))
            with self.assertRaises(ValueError):
                sd.export_report(report, 'txt', directory=directory)

    def test_interactive_export_both_and_offline_sources_status(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}):
            report = sd.discover('example.com')
        report['hosts'] = [{'hostname': 'a.example.com', 'sources': ['crt.sh'], 'dns_status': 'not_checked'}]
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory, \
                patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'}), patch('settings.data_directory', return_value=Path(directory)), \
                patch.object(sd, 'discover', return_value=report), patch('builtins.input', side_effect=['example.com', '', 'a']), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            sd.interactive_discovery()
            self.assertIn('a.example.com', output.getvalue())
            self.assertEqual(len(list((Path(directory) / 'subdomains').glob('*.json'))), 1)
            self.assertEqual(len(list((Path(directory) / 'subdomains').glob('*.csv'))), 1)

    def test_cli_original_interface_offline_navigation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'LittleBrother.py'), '--offline', '--data-dir', directory],
                input='7\nh\nc\n2\n1\nb\ne\n', capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('[7] Sub-domains', result.stdout)
        self.assertIn('LittleBrother(Sub-domains)$', result.stdout)
        self.assertIn('nenhuma fonte externa ou executável foi consultado.', result.stdout)


if __name__ == '__main__':
    unittest.main()
