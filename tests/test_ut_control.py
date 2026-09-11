"""Collector safety guards only; no claim of tablet/DRM validation."""
from pathlib import Path
import platform
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/collect-ut-control.sh'


class ControlCollectorTests(unittest.TestCase):
    def test_posix_shell_syntax(self):
        subprocess.run(['sh', '-n', str(SCRIPT)], check=True)

    def test_unknown_context_stops_before_collection(self):
        run = subprocess.run(['sh', str(SCRIPT), 'not-a-context'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 64)
        self.assertNotIn('Running kernel', run.stdout)

    @unittest.skipIf(platform.machine() in ('aarch64', 'armv8l'),
                     'Non-ARM64 guard only; do not collect local ARM64 host data as tablet evidence')
    def test_host_architecture_guard(self):
        run = subprocess.run(['sh', str(SCRIPT), 'recovery'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertNotIn('Running kernel', run.stdout)
