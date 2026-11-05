"""Offline regressions for native commands, partial routes and safe exports."""
from dataclasses import replace
import csv
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import ANY, patch

from core.pathtrace import (Hop, TraceError, TraceResult, build_command, export_trace,
                            parse_hops, render_csv, render_text, traceroute, validate_host,
                            pathtrace_lookup, TraceProgress, _run_live)

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_OUTPUT = """Tracing route to example.com [1.1.1.1]
over a maximum of 30 hops:
  1    <1 ms    1 ms    2 ms  192.168.0.1
  2     *        *        *     Request timed out.
  3    10 ms   11 ms   12 ms  8.8.8.8
  4    20 ms   21 ms   22 ms  1.1.1.1
Trace complete.
"""
LINUX_OUTPUT = """traceroute to example.com (1.1.1.1), 30 hops max, 60 byte packets
 1  192.168.0.1  0.350 ms  0.236 ms  0.209 ms
 2  * * *
 3  8.8.8.8  4.125 ms  1.0.0.1  4.320 ms  4.200 ms
 4  1.1.1.1  7.123 ms !H  7.200 ms  7.250 ms
"""


def fixture(public_only=False):
    return TraceResult('example.com', '1.1.1.1', parse_hops(WINDOWS_OUTPUT),
                       30, 30, 1000, public_only, '2026-10-23T12:00:00-03:00')


class InputTests(unittest.TestCase):
    def test_hostnames_idna_ipv4_and_ipv6(self):
        for source, expected in [('Example.COM.', 'example.com'), ('café.example', 'xn--caf-dma.example'),
                                 ('localhost', 'localhost'), ('127.0.0.1', '127.0.0.1'),
                                 ('2001:4860:4860::8888', '2001:4860:4860::8888')]:
            with self.subTest(source=source):
                self.assertEqual(validate_host(source), expected)

    def test_shell_flags_urls_and_invalid_ips_are_rejected(self):
        for host in ['', '-h', '--help', ' example.com', 'example.com ', 'https://example.com',
                     'example.com:80', 'example.com/a', 'example.com;whoami', 'x|whoami',
                     'x&whoami', 'x$(whoami)', '`whoami`', 'x\nwhoami', '127.0.0.1/24',
                     '999.999.999.999', '0.0.0.0', '224.0.0.1', '255.255.255.255',
                     '::', 'ff02::1', 'fe80::1%eth0', '[::1]', '..', 'a..example', 'a'*64+'.com']:
            with self.subTest(host=host), self.assertRaises(TraceError):
                validate_host(host)

    def test_invalid_options_do_not_start_subprocess(self):
        with patch('core.pathtrace.subprocess.run') as process:
            for options in ({'max_hops': 0}, {'max_hops': 65}, {'max_hops': True},
                            {'timeout': 0}, {'timeout': 181}, {'timeout': 2.5},
                            {'wait_ms': 99}, {'wait_ms': 5001}, {'public_only': 'yes'}):
                with self.subTest(options=options), self.assertRaises(TraceError):
                    traceroute('1.1.1.1', **options)
            process.assert_not_called()


class CommandTests(unittest.TestCase):
    def test_windows_uses_tracert_options_not_unix_n(self):
        with patch('core.pathtrace._find_executable', return_value=r'C:\Windows\System32\tracert.exe'):
            command = build_command('example.com', 12, 750, 'Windows')
        self.assertEqual(command[1:], ['-d', '-h', '12', '-w', '750', '-4', 'example.com'])
        self.assertNotIn('-n', command)

    def test_linux_options_and_ipv6(self):
        with patch('core.pathtrace._find_executable', return_value='/usr/bin/traceroute'):
            self.assertEqual(build_command('2001:4860:4860::8888', 10, 500, 'Linux')[1:],
                             ['-n', '-m', '10', '-w', '0.5', '-q', '3', '-6', '2001:4860:4860::8888'])

    def test_macos_uses_traceroute6_and_integer_wait(self):
        with patch('core.pathtrace._find_executable', return_value='/usr/sbin/traceroute6') as find:
            command = build_command('::1', 5, 1500, 'Darwin')
        find.assert_called_once_with('Darwin', True)
        self.assertEqual(command[1:], ['-n', '-m', '5', '-w', '2', '-q', '3', '::1'])

    def test_missing_native_tool_has_clear_message(self):
        with patch('core.pathtrace.platform.system', return_value='Linux'), patch('core.pathtrace.shutil.which', return_value=None), patch('core.pathtrace.subprocess.run') as process:
            with self.assertRaisesRegex(TraceError, 'não está instalado'):
                traceroute('1.1.1.1')
            process.assert_not_called()

    def test_unsupported_platform_is_explicit(self):
        with self.assertRaisesRegex(TraceError, 'Windows, Linux e macOS'):
            build_command('example.com', system='Unsupported')


class ParsingTests(unittest.TestCase):
    def test_windows_hops_latency_less_than_one_and_stars(self):
        hops = parse_hops(WINDOWS_OUTPUT)
        self.assertEqual([hop.number for hop in hops], [1, 2, 3, 4])
        self.assertEqual(hops[0].addresses, ('192.168.0.1',))
        self.assertEqual(hops[0].latencies_ms, ('<1', '1', '2'))
        self.assertEqual(hops[1].addresses, ())
        self.assertEqual(hops[1].status, 'sem resposta')

    def test_linux_multiple_responders_annotations_and_decimals(self):
        hops = parse_hops(LINUX_OUTPUT)
        self.assertEqual(hops[2].addresses, ('8.8.8.8', '1.0.0.1'))
        self.assertEqual(hops[0].latencies_ms, ('0.350', '0.236', '0.209'))
        self.assertEqual(hops[-1].markers, ('!H',))

    def test_ipv6_and_portuguese_windows(self):
        hops = parse_hops(' 1 <1 ms <1 ms <1 ms ::1\n 2 * * * Esgotado o tempo limite.\n 3 1,5 ms 2 ms 3 ms 2001:4860:4860::8888\n')
        self.assertEqual(hops[0].addresses, ('::1',))
        self.assertEqual(hops[-1].addresses, ('2001:4860:4860::8888',))
        self.assertEqual(hops[-1].latencies_ms[0], '1.5')

    def test_header_and_unknown_lines_do_not_become_hops(self):
        self.assertEqual(parse_hops('30 hops maximum\n 99 1 ms 8.8.8.8\n error\n'), ())

    def test_public_filter_hides_private_shared_reserved_and_unknown(self):
        result = replace(fixture(True), hops=(
            Hop(1, ('192.168.0.1',), ('1',)), Hop(2, ('100.64.0.1',), ('2',)),
            Hop(3, ('2001:db8::1',), ('3',)), Hop(4, (), ('*', '*', '*')),
            Hop(5, ('10.0.0.1', '8.8.8.8'), ('5', '6')), Hop(6, ('1.1.1.1',), ('7',))))
        self.assertEqual([hop.number for hop in result.visible_hops], [5, 6])
        text, csv_output = render_text(result), render_csv(result)
        for hidden in ('192.168.0.1', '100.64.0.1', '2001:db8::1', '10.0.0.1'):
            self.assertNotIn(hidden, text)
            self.assertNotIn(hidden, csv_output)
        self.assertEqual(result.hops[4].addresses, ('10.0.0.1', '8.8.8.8'))


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0', 'X_BEARER_TOKEN': 'DO-NOT-PASS-THIS'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.native = patch('core.pathtrace._find_executable', return_value=r'C:\Windows\System32\tracert.exe')
        self.native.start()
        self.addCleanup(self.native.stop)
        self.system = patch('core.pathtrace.platform.system', return_value='Windows')
        self.system.start()
        self.addCleanup(self.system.stop)
        self.runner = patch('core.pathtrace.subprocess.run')
        self.process = self.runner.start()
        self.addCleanup(self.runner.stop)
        self.process.return_value = subprocess.CompletedProcess([], 0, WINDOWS_OUTPUT.encode(), b'')

    def test_execution_timeout_no_shell_no_stdin_and_no_credentials(self):
        result = traceroute('example.com', timeout=15)
        self.assertTrue(result.reached)
        self.assertFalse(result.timed_out)
        options = self.process.call_args.kwargs
        self.assertEqual(options['timeout'], 15)
        self.assertFalse(options['shell'])
        self.assertEqual(options['stdin'], subprocess.DEVNULL)
        self.assertNotIn('X_BEARER_TOKEN', options['env'])

    def test_offline_never_starts_process_or_resolves_destination(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), self.assertRaisesRegex(TraceError, 'offline'):
            traceroute('example.com')
        self.process.assert_not_called()

    def test_timeout_preserves_partial_route_without_claiming_destination(self):
        partial = WINDOWS_OUTPUT.split('  3')[0].encode()
        self.process.side_effect = subprocess.TimeoutExpired([], 2, output=partial)
        result = traceroute('example.com', timeout=2)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.reached)
        self.assertEqual(len(result.hops), 2)
        self.assertIn('parcial', render_text(result))

    def test_timeout_without_any_output_is_exportable(self):
        self.process.side_effect = subprocess.TimeoutExpired([], 1)
        result = traceroute('example.com', timeout=1)
        self.assertEqual(result.hops, ())
        self.assertTrue(result.timed_out)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(render_csv(result))))), 1)

    def test_error_and_permission_denied_are_clear(self):
        self.process.return_value = subprocess.CompletedProcess([], 1, b'', b'Permission denied')
        with self.assertRaisesRegex(TraceError, 'Permission denied'):
            traceroute('example.com')
        self.process.side_effect = PermissionError()
        with self.assertRaisesRegex(TraceError, 'negou'):
            traceroute('example.com')

    def test_native_zero_exit_does_not_prove_destination_was_reached(self):
        self.process.return_value = subprocess.CompletedProcess([], 0, b'1 * * *\n', b'')
        self.assertFalse(traceroute('1.1.1.1').reached)

    def test_unrecognized_output_is_not_reported_as_success(self):
        self.process.return_value = subprocess.CompletedProcess([], 0, b'unexpected native output', b'')
        with self.assertRaisesRegex(TraceError, 'saltos reconhecíveis'):
            traceroute('example.com')


class LiveProgressTests(unittest.TestCase):
    def run_script(self, script, callback, *, timeout=3, public_only=False):
        return _run_live([sys.executable, '-B', '-c', script],
                         {'stdin': subprocess.DEVNULL, 'shell': False}, timeout, 30, public_only, callback)

    def test_hops_arrive_before_the_process_finishes(self):
        events, children, running = [], [], []
        native_popen = subprocess.Popen

        def spawn(*args, **kwargs):
            children.append(native_popen(*args, **kwargs))
            return children[-1]

        def observe(event):
            events.append(event)
            if event.kind == 'hop' and event.hop.number == 1:
                running.append(children[0].poll() is None)

        with patch('core.pathtrace.subprocess.Popen', side_effect=spawn):
            result = self.run_script('import time; print("1 1 ms 1 ms 1 ms 8.8.8.8",flush=True); time.sleep(0.5); print("2 2 ms 1.1.1.1",flush=True)', observe)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(running, [True])
        self.assertEqual([e.hop.number for e in events if e.kind == 'hop'], [1, 2])
        self.assertEqual(events[0].kind, 'started')
        self.assertEqual(events[-1].kind, 'finished')

    def test_silent_process_still_produces_heartbeat(self):
        events = []
        self.run_script('import time; time.sleep(1.3)', events.append)
        self.assertTrue(any(e.kind == 'waiting' and e.elapsed >= 1 for e in events))

    def test_timeout_preserves_unterminated_hop(self):
        events = []
        with self.assertRaises(subprocess.TimeoutExpired) as error:
            self.run_script('import time; print("1 1 ms 8.8.8.8",end="",flush=True); time.sleep(10)', events.append, timeout=0.5)
        self.assertIn(b'8.8.8.8', error.exception.stdout)
        self.assertEqual(events[-1].kind, 'timeout')
        self.assertEqual([e.hop.addresses for e in events if e.kind == 'hop'], [('8.8.8.8',)])

    def test_live_filter_does_not_expose_raw_header_private_or_unknown_hops(self):
        events = []
        script = ('print("Tracing route [192.168.0.1]"); print("1 1 ms 192.168.0.1"); '
                  'print("2 * * *"); print("3 1 ms 10.0.0.1 2 ms 8.8.8.8"); '
                  'print("4 1 ms 2001:db8::1 2 ms 2001:4860:4860::8888")')
        self.run_script(script, events.append, public_only=True)
        hops = [e.hop for e in events if e.kind == 'hop']
        self.assertEqual([h.number for h in hops], [3, 4])
        self.assertEqual(hops[0].addresses, ('8.8.8.8',))
        for private in ('192.168.0.1', '10.0.0.1', '2001:db8::1'):
            self.assertNotIn(private, repr(events))

    def test_callback_interruption_terminates_child(self):
        native_popen, children = subprocess.Popen, []

        def spawn(*args, **kwargs):
            children.append(native_popen(*args, **kwargs))
            return children[-1]

        def interrupt(event):
            raise KeyboardInterrupt

        with patch('core.pathtrace.subprocess.Popen', side_effect=spawn), self.assertRaises(KeyboardInterrupt):
            self.run_script('import time; time.sleep(10)', interrupt)
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdout.closed)

    def test_live_capture_rejects_excessive_output(self):
        with patch('core.pathtrace.MAX_OUTPUT', 64), self.assertRaisesRegex(TraceError, 'saída excessiva'):
            self.run_script('print("x"*4096,flush=True)', lambda event: None)


class ExportAndMenuTests(unittest.TestCase):
    def test_csv_columns_and_filters_match_text(self):
        rows = list(csv.DictReader(io.StringIO(render_csv(fixture(True)))))
        self.assertEqual([row['hop'] for row in rows], ['3', '4'])
        self.assertEqual(rows[-1]['ips'], '1.1.1.1')
        self.assertEqual(rows[-1]['timeout_total_s'], '30')

    def test_exports_are_private_new_files_with_correct_encoding(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            txt = export_trace(fixture(True), 'txt', directory)
            csv_path = export_trace(fixture(True), 'csv', directory)
            self.assertEqual(txt.parent, Path(directory).resolve() / 'traces')
            self.assertNotEqual(txt, csv_path)
            self.assertIn('Pathtrace', txt.read_text(encoding='utf-8'))
            self.assertTrue(csv_path.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertNotIn('192.168.0.1', csv_path.read_text(encoding='utf-8-sig'))

    def test_invalid_export_format_and_symlink_directory_are_refused(self):
        with self.assertRaises(TraceError):
            export_trace(fixture(), '../csv')
        with tempfile.TemporaryDirectory(dir=ROOT / '.work') as directory:
            with patch('core.pathtrace.Path.is_symlink', return_value=True), self.assertRaises(TraceError):
                export_trace(fixture(), 'txt', directory)

    def test_csv_formula_values_are_escaped(self):
        rows = list(csv.DictReader(io.StringIO(render_csv(replace(fixture(), host='=formula')))))
        self.assertEqual(rows[0]['host'], "'=formula")

    def test_interactive_lookup_defaults_and_both_export_formats(self):
        def trace(*args, **kwargs):
            callback = kwargs['on_progress']
            callback(TraceProgress(0, 'started'))
            callback(TraceProgress(1, 'waiting'))
            callback(TraceProgress(2, 'hop', Hop(3, ('8.8.8.8',), ('10', '11', '12'))))
            callback(TraceProgress(3, 'timeout'))
            return fixture(True)

        with patch('builtins.input', side_effect=['example.com', '', '', '', 's', '1', '2', '']), patch('core.pathtrace.traceroute', side_effect=trace) as run, patch('core.pathtrace.export_trace', return_value=Path('report')) as export, patch('sys.stdout', new_callable=io.StringIO) as output:
            with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '0'}):
                pathtrace_lookup()
            run.assert_called_once_with('example.com', max_hops=30, timeout=30, public_only=True, wait_ms=1000, on_progress=ANY)
            self.assertEqual([call.args[1] for call in export.call_args_list], ['csv', 'txt'])
            self.assertIn('[  1.0s] Diagnóstico em andamento', output.getvalue())
            self.assertIn('Hop 03 | 8.8.8.8 | RTT: 10 / 11 / 12 ms', output.getvalue())
            self.assertIn('Timeout total atingido; preparando os resultados parciais.', output.getvalue())

    def test_interactive_offline_does_not_prompt_or_probe(self):
        with patch.dict(os.environ, {'LITTLEBROTHER_OFFLINE': '1'}), patch('builtins.input') as prompt, patch('core.pathtrace.traceroute') as run, patch('sys.stdout', new_callable=io.StringIO):
            pathtrace_lookup()
            prompt.assert_not_called()
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
