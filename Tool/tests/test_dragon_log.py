import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um import dragon_log as log


class LogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name) / 'logs'
        log.shutdown_logging()

    def tearDown(self):
        log.shutdown_logging()
        self.temp.cleanup()

    def text(self):
        for handler in log.get_logger().handlers:
            handler.flush()
        return (self.dir / log.LOG_NAME).read_text(encoding='utf-8')

    def test_redacts_home_and_user_name_but_keeps_the_rest_of_the_path(self):
        home = str(Path.home())
        other = 'C:/Users' + '/SomeoneElse/x/y.gmd'  # split so the public-export path scan stays clean
        out = log.redact(f'failed at {home}\\Documents\\a.vrm and {other}')
        self.assertNotIn(home, out)
        self.assertNotIn('SomeoneElse', out)
        self.assertIn('Documents', out)
        self.assertIn('x/y.gmd', out)
        with patch.dict(os.environ, {'USERNAME': 'zed_the_user'}):
            self.assertNotIn('zed_the_user', log.redact('hello zed_the_user!'))

    def test_log_lines_are_redacted_when_written(self):
        log.setup_logging(self.dir)
        log.get_logger().info('open %s', str(Path.home()) + '\\secret\\a.vrm')
        text = self.text()
        self.assertNotIn(str(Path.home()), text)
        self.assertIn('secret', text)

    def test_setup_is_idempotent_and_rotation_caps_the_disk_use(self):
        log.setup_logging(self.dir, max_bytes=2000, backups=2)
        log.setup_logging(self.dir, max_bytes=2000, backups=2)
        self.assertEqual(len([h for h in log.get_logger().handlers if getattr(h, '_vrmdragon', False)]), 1)
        for i in range(400):
            log.get_logger().info('line %d %s', i, 'x' * 40)
        files = sorted(p.name for p in self.dir.iterdir())
        self.assertLessEqual(len(files), 3)
        self.assertTrue(sum(p.stat().st_size for p in self.dir.iterdir()) < 3 * 2200)

    def test_unwritable_log_folder_never_breaks_the_app(self):
        blocker = Path(self.temp.name) / 'file'
        blocker.write_text('x')
        logger = log.setup_logging(blocker / 'logs')
        logger.info('still fine')
        log.log_exception('context', ValueError('boom'))

    def test_run_logged_records_success_and_failure_with_full_output(self):
        log.setup_logging(self.dir)
        ok = log.run_logged([sys.executable, '-c', 'print("hello out")'], 'unit ok', 30)
        self.assertEqual(ok.returncode, 0)
        bad = log.run_logged([sys.executable, '-c',
                              'import sys;print("O"*10);sys.stderr.write("Traceback marker\\n");sys.exit(3)'],
                             'unit bad', 30)
        self.assertEqual(bad.returncode, 3)
        text = self.text()
        self.assertIn('unit ok finished', text)
        self.assertIn('unit bad exited with 3', text)
        self.assertIn('Traceback marker', text)

    def test_huge_subprocess_output_is_clipped(self):
        log.setup_logging(self.dir)
        log.run_logged([sys.executable, '-c', 'import sys;print("A"*300000);sys.exit(1)'], 'big', 60)
        text = self.text()
        self.assertIn('characters omitted', text)
        self.assertLess(len(text), 130_000)

    def test_timeout_is_logged_and_reraised(self):
        log.setup_logging(self.dir)
        with self.assertRaises(subprocess.TimeoutExpired):
            log.run_logged([sys.executable, '-c', 'import time;time.sleep(5)'], 'slow', 0.3)
        self.assertIn('slow timed out', self.text())

    def test_exception_traceback_is_logged(self):
        log.setup_logging(self.dir)
        try:
            raise RuntimeError('kaboom')
        except RuntimeError as exc:
            log.log_exception('conversion failed', exc)
        text = self.text()
        self.assertIn('conversion failed: kaboom', text)
        self.assertIn('Traceback', text)

    def test_debug_report_has_environment_failures_and_log_and_is_redacted(self):
        log.setup_logging(self.dir)
        log.get_logger().info('before %s', str(Path.home()) + '\\x.vrm')
        outputs = Path(self.temp.name) / 'outputs'
        (outputs / 'run1').mkdir(parents=True)
        (outputs / 'run1' / 'variant-coverage.json').write_text(
            json.dumps({'status': 'VARIANT_BATCH_FAILED', 'error': 'UV missing in source VRM: Body'}), encoding='utf-8')
        report = log.create_debug_report(self.dir, outputs)
        text = report.read_text(encoding='utf-8')
        for needle in ('tool_fingerprint', 'python:', 'recent failed runs', 'UV missing in source VRM: Body',
                       'newest log text', 'before '):
            self.assertIn(needle, text)
        self.assertNotIn(str(Path.home()), text)

    def test_old_debug_reports_are_pruned(self):
        self.dir.mkdir(parents=True)
        for i in range(14):
            path = self.dir / f'debug-report-20260101_0000{i:02d}.txt'
            path.write_text('x')
            os.utime(path, (1000 + i, 1000 + i))
        log.create_debug_report(self.dir, Path(self.temp.name) / 'none')
        self.assertLessEqual(len(list(self.dir.glob('debug-report-*.txt'))), log.REPORTS_KEPT)

    def test_delete_logs_only_removes_this_tools_files(self):
        log.setup_logging(self.dir)
        log.get_logger().info('hello')
        (self.dir / 'debug-report-20260101_000000.txt').write_text('r')
        (self.dir / 'keep.txt').write_text('mine')
        self.assertGreater(log.log_files_size(self.dir), 0)
        removed = log.delete_logs(self.dir)
        self.assertGreaterEqual(removed, 2)
        self.assertTrue((self.dir / 'keep.txt').is_file())
        self.assertFalse((self.dir / log.LOG_NAME).exists())

    def test_failure_summary_prefers_the_error_lines_over_noise(self):
        output = chr(10).join([
            'Error: Python: Traceback (most recent call last):',
            '  File "importer.py", line 3, in load',
            'OSError: load: x/yakuza_shader.blend failed to open blend file',
            '<Vector (0.0000, 0.0000, 0.0000, 1.0000)>	<Vector (1.0000, 1.0000, 1.0000, 0.0000)>',
            'Blender quit'])
        text = log.failure_summary(output, '')
        self.assertIn('failed to open blend file', text)
        self.assertNotIn('Vector', text)
        self.assertNotIn('File "importer.py"', text)

    def test_failure_summary_falls_back_to_the_last_lines_and_is_capped(self):
        quiet = chr(10).join(f'line {i}' for i in range(40))
        self.assertTrue(log.failure_summary(quiet, '').endswith('line 39'))
        self.assertLessEqual(len(log.failure_summary('Error: ' + 'x' * 5000, '')), 1500)

    def test_fingerprint_changes_with_the_source(self):
        root = Path(self.temp.name) / 'tree'
        (root / 'Tool' / 'um').mkdir(parents=True)
        (root / 'Tool' / 'um' / 'a.py').write_text('x = 1')
        first = log.tool_fingerprint(root)
        (root / 'Tool' / 'um' / 'a.py').write_text('x = 2')
        self.assertNotEqual(first, log.tool_fingerprint(root))


if __name__ == '__main__':
    unittest.main()
