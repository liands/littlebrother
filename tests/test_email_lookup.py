from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import email_lookup as lookup
from lib.email_config import configuration_path, load_email_config
from lib.http import IntegrationError
from test_http import FakeResponse

ROOT = Path(__file__).resolve().parents[1]
HUNTER = {'data': {'email': 'user@example.com', 'status': 'valid', 'score': 99,
                  'regexp': True, 'mx_records': True, 'smtp_check': True, 'disposable': False, 'accept_all': False}}
KICKBOX = {'email': 'user@example.com', 'success': True, 'result': 'deliverable', 'reason': 'accepted_email',
           'sendex': 0.95, 'role': False, 'free': False, 'disposable': False, 'accept_all': False, 'did_you_mean': None}


def config():
    return {'keys': {'HIBP_API_KEY': 'a'*32, 'HUNTER_API_KEY': 'hunter-secret', 'KICKBOX_API_KEY': 'kickbox-secret'},
            'hibp_enabled': True, 'hunter_enabled': True, 'kickbox_enabled': True,
            'hunter_max_attempts': 2, 'kickbox_timeout_ms': 6000}


class EmailConfigurationTests(unittest.TestCase):
    def test_template_loads_with_no_keys_and_bounded_defaults(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_CONFIG': str(ROOT/'configuracao.exemplo.ini')}, clear=True):
            settings = load_email_config()
        self.assertFalse(any(settings['keys'].values()))
        self.assertEqual(settings['hunter_max_attempts'], 2)
        self.assertEqual(settings['kickbox_timeout_ms'], 6000)

    def test_keys_percent_signs_environment_priority_and_reload(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.work') as folder:
            file = Path(folder)/'config.ini'
            file.write_text('[api_keys]\nHUNTER_API_KEY = abc%123\nKICKBOX_API_KEY = from-file\n[email_lookup]\nkickbox_enabled = false\n', encoding='utf-8')
            with patch.dict(os.environ, {'LITTLEBROTHER_CONFIG': str(file), 'KICKBOX_API_KEY': 'from-env'}, clear=True):
                self.assertEqual(load_email_config()['keys']['HUNTER_API_KEY'], 'abc%123')
                self.assertEqual(load_email_config()['keys']['KICKBOX_API_KEY'], 'from-env')
                self.assertFalse(load_email_config()['kickbox_enabled'])
                file.write_text('[api_keys]\nHUNTER_API_KEY=changed\n', encoding='utf-8')
                self.assertEqual(load_email_config()['keys']['HUNTER_API_KEY'], 'changed')

    def test_absent_file_uses_defaults_without_creating_it(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.work') as folder:
            file = Path(folder)/'missing.ini'
            with patch.dict(os.environ, {'LITTLEBROTHER_CONFIG': str(file)}, clear=True):
                self.assertFalse(any(load_email_config()['keys'].values()))
            self.assertFalse(file.exists())

    def test_parse_errors_unknown_options_and_bad_numbers_hide_secrets(self):
        cases = ('SECRET=bad-line', '[api_keys]\nHUNTER_API_KEY=SECRET\nHUNTER_API_KEY=duplicate',
                 '[api_keys]\nSECRET=bad-option', '[email_lookup]\nhunter_max_attempts=999',
                 '[email_lookup]\nkickbox_timeout_ms=30000', '[email_lookup]\nhunter_enabled=SECRET')
        with tempfile.TemporaryDirectory(dir=ROOT/'.work') as folder:
            file = Path(folder)/'config.ini'
            for content in cases:
                file.write_text(content, encoding='utf-8')
                with patch.dict(os.environ, {'LITTLEBROTHER_CONFIG': str(file)}, clear=True), self.subTest(content=content):
                    with self.assertRaises(ValueError) as error:
                        load_email_config()
                    self.assertNotIn('SECRET', str(error.exception))

    def test_config_does_not_mutate_environment_or_expose_keys_in_diagnostics(self):
        import LittleBrother
        with tempfile.TemporaryDirectory(dir=ROOT/'.work') as folder:
            file = Path(folder)/'config.ini'
            file.write_text('[api_keys]\nHUNTER_API_KEY=PRIVATE-KEY-TEST\n', encoding='utf-8')
            with patch.dict(os.environ, {'LITTLEBROTHER_CONFIG': str(file), 'LITTLEBROTHER_DATA_DIR': str(Path(folder)/'data')}, clear=True), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(LittleBrother.main(['--check']), 0)
                self.assertNotIn('PRIVATE-KEY-TEST', output.getvalue())
                self.assertIn('HUNTER_API_KEY: configurado', output.getvalue())
                self.assertNotIn('HUNTER_API_KEY', os.environ)

    def test_configuration_helper_creates_once_and_never_overwrites(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.work') as folder:
            file = Path(folder)/'private'/'config.ini'
            environment = dict(os.environ, LITTLEBROTHER_CONFIG=str(file))
            command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'configurar-apis.ps1'), '-SomenteCriar']
            if os.name != 'nt':
                self.skipTest('Windows configuration helper')
            first = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            file.write_text('[api_keys]\nHUNTER_API_KEY=KEEP-THIS-KEY\n', encoding='utf-8')
            second = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=10)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn('KEEP-THIS-KEY', file.read_text(encoding='utf-8'))
            self.assertNotIn('KEEP-THIS-KEY', second.stdout + second.stderr)


class UnifiedEmailTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_invalid_email_never_starts_providers(self):
        for email in ('', 'a..b@example.com', '.user@example.com', 'a@localhost', 'user@127.0.0.1',
                      'https://x@example.com', 'user@example.com\n', 'a@@b.com', 'x@-bad.com', 'x@e.com/a'):
            with patch.object(lookup, '_provider') as provider, self.subTest(email=email), self.assertRaises(ValueError):
                lookup.lookup_email(email, config=config())
            provider.assert_not_called()
        self.assertEqual(lookup.validate_email('User+tag@BÜCHER.DE'), 'User+tag@xn--bcher-kva.de')

    def test_offline_does_not_read_keys_or_start_providers(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), patch.object(lookup, '_provider') as provider, \
                patch.object(lookup, 'load_email_config', side_effect=AssertionError('read config')):
            report = lookup.lookup_email('user@example.com')
        self.assertTrue(all(item['state'] == 'offline' for item in report['providers']))
        provider.assert_not_called()

    def test_missing_and_disabled_sources_never_request(self):
        settings = config()
        settings['keys'] = {key: '' for key in settings['keys']}
        settings['hunter_enabled'] = False
        with patch.object(lookup, '_provider') as provider:
            report = lookup.lookup_email('user@example.com', config=settings)
        self.assertEqual([item['state'] for item in report['providers']], ['not_configured','disabled','not_configured','disabled'])
        provider.assert_not_called()

    def test_hunter_status_flags_header_key_and_long_request_timeout(self):
        with patch.object(lookup, 'get_json', return_value=deepcopy(HUNTER)) as request:
            result = lookup._provider('Hunter','user@example.com','hunter-secret',config())
        self.assertEqual(result['data']['category'], 'favorable')
        self.assertIsNone(result['data']['flags']['role'])
        self.assertNotIn('hunter-secret', request.call_args.args[0])
        self.assertNotIn('api_key', request.call_args.kwargs['params'])
        self.assertEqual(request.call_args.kwargs['headers'], {'X-API-KEY':'hunter-secret'})
        self.assertEqual(request.call_args.kwargs['read_timeout'],25)

    def test_hunter_202_is_bounded_and_keeps_pending_distinct(self):
        pending = IntegrationError('raw SECRET',code='http_202')
        with patch.object(lookup, 'get_json', side_effect=[pending,deepcopy(HUNTER)]) as request, patch.object(lookup.time,'sleep'):
            self.assertEqual(lookup._provider('Hunter','user@example.com','key',config())['state'],'ok')
            self.assertEqual(request.call_count,2)
        with patch.object(lookup, 'get_json', side_effect=pending) as request, patch.object(lookup.time,'sleep'):
            result = lookup._provider('Hunter','user@example.com','key',config())
            self.assertEqual(result['state'],'pending')
            self.assertEqual(request.call_count,2)
            self.assertNotIn('SECRET',json.dumps(result))

    def test_hunter_deprecated_result_is_not_used_as_validity(self):
        with patch.object(lookup, 'get_json', return_value={'data': {'result':'deliverable','email':'user@example.com'}}):
            self.assertEqual(lookup._provider('Hunter','user@example.com','key',config())['state'],'error')

    def test_hunter_demo_never_confirms_real_email(self):
        data = deepcopy(HUNTER)
        data['data']['email'] = 'dummy@example.org'
        with patch.object(lookup, 'get_json', return_value=data):
            result=lookup._provider('Hunter','user@example.com','test-api-key',config())
        report={'email':'user@example.com','providers':[result]}
        self.assertIn('DEMONSTRAÇÃO',lookup.render_email_lookup(report))
        self.assertIn('inconclusiva',lookup.deliverability_summary(report))

    def test_kickbox_score_typo_and_parameters(self):
        data = deepcopy(KICKBOX)
        data['did_you_mean']='user@example.org'
        data['role']=True
        with patch.object(lookup,'get_json',return_value=data) as request:
            result=lookup._provider('Kickbox','user@example.com','kickbox-secret',config())
        self.assertEqual(result['state'],'ok')
        self.assertEqual(result['data']['suggestion'],'user@example.org')
        self.assertTrue(result['data']['flags']['role'])
        self.assertEqual(request.call_args.kwargs['params']['timeout'],6000)
        self.assertEqual(request.call_args.kwargs['params']['apikey'],'kickbox-secret')
        self.assertEqual(request.call_count,1)

    def test_kickbox_false_success_and_raw_message_are_not_empty_success(self):
        with patch.object(lookup,'get_json',return_value={'success':False,'message':'url?apikey=SECRET'}):
            result=lookup._provider('Kickbox','user@example.com','key',config())
        self.assertEqual(result['state'],'error')
        self.assertNotIn('SECRET',json.dumps(result))

    def test_kickbox_sandbox_results_do_not_confirm_deliverability(self):
        settings=config()
        settings['kickbox_sandbox']=True
        with patch.object(lookup,'get_json',return_value=deepcopy(KICKBOX)):
            result=lookup._provider('Kickbox','user@example.com','sandbox-key',settings)
        report={'email':'user@example.com','providers':[result]}
        self.assertIn('SANDBOX',lookup.render_email_lookup(report))
        self.assertIn('inconclusiva',lookup.deliverability_summary(report))

    def test_kickbox_test_prefix_is_conservatively_marked_demo(self):
        with patch.object(lookup,'get_json',return_value=deepcopy(KICKBOX)):
            result=lookup._provider('Kickbox','user@example.com','test_dummy-key',config())
        self.assertTrue(result['data']['demo'])

    def test_bad_scores_booleans_and_mismatched_emails_are_rejected(self):
        for provider, fixture in [('Hunter',HUNTER),('Kickbox',KICKBOX)]:
            for changes in ({'email':'other@example.com'},{'score':True} if provider=='Hunter' else {'sendex':2},
                            {'accept_all':'false'}, {'score':float('nan')} if provider=='Hunter' else {'sendex':float('inf')}):
                data=deepcopy(fixture)
                (data['data'] if provider=='Hunter' else data).update(changes)
                with patch.object(lookup,'get_json',return_value=data), self.subTest(provider=provider,changes=changes):
                    self.assertEqual(lookup._provider(provider,'user@example.com','key',config())['state'],'error')

    def test_accept_all_and_unknown_do_not_confirm_mailbox(self):
        data=deepcopy(HUNTER)
        data['data']['status']='accept_all'
        with patch.object(lookup,'get_json',return_value=data):
            result=lookup._provider('Hunter','user@example.com','key',config())
        self.assertIn('não confirmada',lookup.deliverability_summary({'providers':[result]}))
        data['data']['status']='unknown'
        with patch.object(lookup,'get_json',return_value=data):
            result=lookup._provider('Hunter','user@example.com','key',config())
        self.assertIn('inconclusiva',lookup.deliverability_summary({'providers':[result]}))

    def test_hibp_explicit_config_key_and_exposure_stays_independent(self):
        with patch.object(lookup,'leaked') as client:
            client.return_value.email.return_value=[]
            result=lookup._provider('HIBP','user@example.com','a'*32,config())
        client.return_value.email.assert_called_once_with('user@example.com',api_key='a'*32)
        report={'email':'user@example.com','providers':[result]}
        self.assertIn('Nenhum vazamento',lookup.render_email_lookup(report))
        self.assertIn('inconclusiva',lookup.deliverability_summary(report))

    def test_each_provider_error_is_sanitized_and_classified(self):
        for code,state in [('http_401','auth_error'),('http_403','auth_error'),('http_429','rate_limited'),
                           ('http_451','restricted'),('timeout','error')]:
            with patch.object(lookup,'get_json',side_effect=IntegrationError('SECRET in URL',code=code)):
                result=lookup._provider('Hunter','user@example.com','key',config())
            self.assertEqual(result['state'],state)
            self.assertNotIn('SECRET',json.dumps(result))

    def test_combined_report_survives_one_source_failing_and_hides_keys(self):
        def fetch(url,**kwargs):
            if 'hunter.io' in url:
                raise IntegrationError('reflected hunter-secret',code='http_429')
            return deepcopy(KICKBOX)
        with patch.object(lookup,'get_json',side_effect=fetch),patch.object(lookup,'leaked') as client:
            client.return_value.email.return_value=[{'Title':'Breach','Domain':'example.net','Date':'2020-01-01'}]
            report=lookup.lookup_email('user@example.com',config=config())
        self.assertEqual([item['state'] for item in report['providers']],['ok','rate_limited','ok','disabled'])
        text=lookup.render_email_lookup(report)
        self.assertIn('Breach',text)
        self.assertIn('Sendex',text)
        self.assertNotIn('hunter-secret',text)
        self.assertNotIn('kickbox-secret',json.dumps(report))

    def test_conflicting_providers_are_not_averaged(self):
        hunter={'provider':'Hunter','state':'ok','data':{'category':'favorable'}}
        kickbox={'provider':'Kickbox','state':'ok','data':{'category':'unfavorable'}}
        self.assertIn('divergentes',lookup.deliverability_summary({'providers':[hunter,kickbox]}))

    def test_http_override_is_bounded_and_errors_do_not_echo_query_keys(self):
        from lib import http
        with patch('lib.http.requests.Session') as factory:
            session=factory.return_value.__enter__.return_value
            session.get.return_value=FakeResponse(b'{}')
            http.get_json('https://api.hunter.io/v2/email-verifier',read_timeout=25)
            self.assertEqual(session.get.call_args.kwargs['timeout'],(5,25))
            for value in (True,0,26,'25'):
                with self.assertRaises(IntegrationError):
                    http.get_json('https://api.hunter.io/v2/email-verifier',read_timeout=value)
            session.get.return_value=FakeResponse(b'url?apikey=SECRET',status=403)
            with self.assertRaises(IntegrationError) as error:
                http.get_json('https://api.kickbox.com/v2/verify',params={'apikey':'SECRET'})
            self.assertNotIn('SECRET',str(error.exception))

    def test_existing_lookup_menu_seven_remains_available_offline(self):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'LittleBrother.py'),'--offline','--data-dir',str(ROOT/'.work')],
                              input='1\n7\nb\ne\n',capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertIn('[7] Email lookup',result.stdout)
        self.assertIn('nenhuma consulta de email foi iniciada',result.stdout)


if __name__=='__main__':
    unittest.main()
