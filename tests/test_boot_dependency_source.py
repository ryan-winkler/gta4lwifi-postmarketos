"""Check the applied board repair and package order without hardware writes."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from test_donor_bridge import ROOT, PORT, apply_subset
sys.path.insert(0, str(ROOT / 'tools'))
from package_sources import patch_paths


class BootDependencySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.board, _ = apply_subset(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_enables_parent_and_selected_dma(self):
        for label in ('qupv3_id_0', 'gpi_dma0'):
            self.assertIn('&' + label + ' {\n\tstatus = "okay";\n};', self.board)

    def test_connects_both_sd_states(self):
        self.assertIn('pinctrl-names = "default", "sleep";', self.board)
        self.assertIn('pinctrl-0 = <&gta4lwifi_sdc2_default &gta4lwifi_sd_cd_default>;', self.board)
        self.assertIn('pinctrl-1 = <&gta4lwifi_sdc2_sleep &gta4lwifi_sd_cd_sleep>;', self.board)

    def test_preserves_boot_selector_clock_and_touch(self):
        for declaration in ('qcom,board-id = <0x1000b 0x0>;',
                            'clock-frequency = <32764>;',
                            'himax,rst-gpio = <&tlmm 31 GPIO_ACTIVE_HIGH>;',
                            'himax,irq-gpio = <&tlmm 80 GPIO_ACTIVE_HIGH>;',
                            'cd-gpios = <&tlmm 88 GPIO_ACTIVE_LOW>;'):
            self.assertIn(declaration, self.board)

    def test_sd_labels_are_defined_locally(self):
        for label in ('gta4lwifi_sdc2_default', 'gta4lwifi_sdc2_sleep',
                      'gta4lwifi_sd_cd_default', 'gta4lwifi_sd_cd_sleep'):
            self.assertIn(label + ': ', self.board)
        self.assertNotIn('&sdc2_on_state', self.board)
        self.assertNotIn('&sdc2_off_state', self.board)

    def test_package_order(self):
        paths = patch_paths(PORT)
        self.assertEqual(len(paths), 5)
        self.assertEqual(paths[-1].name, '0005-enable-geni-and-sd-pinctrl.patch')

    def test_unlisted_patch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            for path in PORT.iterdir():
                if path.is_file():
                    shutil.copyfile(path, copy / path.name)
            (copy / 'unlisted.patch').write_text('not configured')
            with self.assertRaises(ValueError):
                patch_paths(copy)

    def test_checksum_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            for path in PORT.iterdir():
                if path.is_file():
                    shutil.copyfile(path, copy / path.name)
            patch = copy / '0005-enable-geni-and-sd-pinctrl.patch'
            patch.write_text(patch.read_text() + '\n')
            with self.assertRaises(ValueError):
                patch_paths(copy)
