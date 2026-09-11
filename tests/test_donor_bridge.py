"""Offline parsing, applied-source and generated-C regressions; no hardware writes."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import donor_bridge as bridge
import regenerate_donor as regen
from fdt_reader import fdt_nodes

PORT = ROOT / 'device/testing/linux-postmarketos-qcom-sm6115'
BOARD = 'arch/arm64/boot/dts/qcom/sm6115-samsung-gta4lwifi.dts'
DRIVER = 'drivers/input/touchscreen/hxchipset/himax_platform.c'
DTC = os.environ.get('DTC', 'dtc')


def minimal_fdt(properties=None):
    properties = properties or {'qcom,msm-id': struct.pack('>4I', 417, 65536, 444, 65536)}
    strings = bytearray()
    tree = bytearray(struct.pack('>I', 1) + b'\0\0\0\0')
    for name, data in properties.items():
        off = len(strings)
        strings += name.encode() + b'\0'
        tree += struct.pack('>III', 3, len(data), off) + data
        tree += b'\0' * ((-len(data)) % 4)
    tree += struct.pack('>II', 2, 9)
    total = 56 + len(tree) + len(strings)
    return struct.pack('>10I', 0xd00dfeed, total, 56, 56 + len(tree), 40, 17, 16, 0, len(strings), len(tree)) + bytes(16) + tree + strings


def boot_image(dtb=None, appended=False):
    dtb = minimal_fdt() if dtb is None else dtb
    header = bytearray(4096)
    header[:8] = b'ANDROID!'
    kernel = gzip.compress(b'fake kernel for packaging test', mtime=0)
    if appended:
        kernel += dtb
    ramdisk = b'ramdisk'
    struct.pack_into('<10I', header, 8, len(kernel), 0x8000, len(ramdisk), 0x20000000, 0, 0, 0x1e00000, 4096, 2, 0)
    struct.pack_into('<IQI', header, 1632, 0, 0, 1660)
    struct.pack_into('<IQ', header, 1648, len(dtb), 0x1f00000)
    pad = lambda b: b + bytes((-len(b)) % 4096)
    return bytes(header) + pad(kernel) + pad(ramdisk) + pad(dtb)


def dtbo_table(count=1, shared=False):
    fdt = minimal_fdt({'qcom,board-id': struct.pack('>2I', 65547, 0)})
    start = 32 + 32 * count
    entries = b''.join(struct.pack('>8I', len(fdt), start if shared else start + i * len(fdt), i, 0, 0, 0, 0, 0) for i in range(count))
    payload = fdt if shared else fdt * count
    return struct.pack('>8I', 0xd7b7ab1e, start + len(payload), 32, 32, count, 32, 4096, 0) + entries + payload


def modify_u32(data, offset, value, endian='>'):
    out = bytearray(data)
    struct.pack_into(endian + 'I', out, offset, value)
    return bytes(out)


def apply_subset(target):
    subprocess.run(['git', 'init', '-q', str(target)], check=True)
    patches = sorted(PORT.glob('000[1-4]-*.patch'))
    if len(patches) != 4:
        raise AssertionError('Expected four active patches')
    for patch in patches:
        includes = [f'--include={BOARD}', '--include=drivers/input/touchscreen/hxchipset/*']
        subprocess.run(['git', 'apply', '--check', *includes, str(patch)], cwd=target, check=True)
        subprocess.run(['git', 'apply', *includes, str(patch)], cwd=target, check=True)
    return (target / BOARD).read_text(), (target / DRIVER).read_text()


def function_body(source, name):
    start = source.index('static int ' + name + '(')
    brace = source.index('{', start)
    level = 1
    pos = brace + 1
    while level:
        if source[pos] == '{': level += 1
        if source[pos] == '}': level -= 1
        pos += 1
    return source[start:pos]


class ContainerTests(unittest.TestCase):
    def test_fdt_series(self):
        blob = minimal_fdt()
        self.assertEqual(bridge.fdt_series(blob + blob + bytes(12)), [blob, blob])

    def test_fdt_rejects_magic_scanning(self):
        with self.assertRaises(ValueError): bridge.fdt_series(b'junk' + minimal_fdt())

    def test_fdt_rejects_truncation(self):
        with self.assertRaises(ValueError): bridge.fdt_series(minimal_fdt()[:-1])

    def test_fdt_rejects_oversized_totalsize(self):
        with self.assertRaises(ValueError): bridge.fdt_series(modify_u32(minimal_fdt(), 4, 100000))

    def test_fdt_no_trees(self):
        with self.assertRaises(ValueError): bridge.fdt_series(bytes(40))

    def test_boot_two_tree_locations(self):
        report = bridge.inventory(boot_image(appended=True))
        self.assertEqual([t['role'] for t in report['trees']], ['header-dtb', 'appended-dtb'])
        self.assertEqual(report['trees'][0]['sha256'], report['trees'][1]['sha256'])
        self.assertFalse(report['hardware_verified'])

    def test_boot_header_offsets(self):
        h, sections = bridge.boot_sections(boot_image())
        self.assertEqual(h['dtb_addr'], 0x1f00000)
        self.assertEqual(h['header_size'], 1660)
        self.assertEqual(sections['ramdisk'], b'ramdisk')

    def test_boot_missing_dtb_explicit_note(self):
        report = bridge.inventory(boot_image(dtb=b''))
        self.assertIn('No separate header DTB section', report['notes'])

    def test_boot_invalid_version(self):
        with self.assertRaises(ValueError): bridge.inventory(modify_u32(boot_image(), 40, 3, '<'))

    def test_boot_wrong_header_size(self):
        with self.assertRaises(ValueError): bridge.inventory(modify_u32(boot_image(), 1644, 1648, '<'))

    def test_boot_truncated(self):
        with self.assertRaises(ValueError): bridge.inventory(boot_image()[:-1])

    def test_boot_misaligned_page(self):
        with self.assertRaises(ValueError): bridge.inventory(modify_u32(boot_image(), 36, 4000, '<'))

    def test_dtbo_table_entries(self):
        report = bridge.inventory(dtbo_table(2))
        self.assertEqual([t['id'] for t in report['trees']], [0, 1])
        self.assertEqual(report['trees'][0]['board_id'], [65547, 0])

    def test_dtbo_shared_payload_valid(self):
        self.assertEqual(len(bridge.dtbo_entries(dtbo_table(2, True))), 2)

    def test_dtbo_overlap_rejected(self):
        with self.assertRaises(ValueError): bridge.dtbo_entries(modify_u32(dtbo_table(2), 68, 100))

    def test_dtbo_payload_before_table(self):
        with self.assertRaises(ValueError): bridge.dtbo_entries(modify_u32(dtbo_table(), 36, 32))

    def test_dtbo_payload_outside_total(self):
        with self.assertRaises(ValueError): bridge.dtbo_entries(modify_u32(dtbo_table(), 36, 90000))

    def test_dtbo_version_one_rejected(self):
        with self.assertRaises(ValueError): bridge.dtbo_entries(modify_u32(dtbo_table(), 28, 1))

    def test_dtbo_truncated_table(self):
        with self.assertRaises(ValueError): bridge.dtbo_entries(dtbo_table()[:50])

    def test_dtbo_excessive_count(self):
        with self.assertRaises(ValueError): bridge.dtbo_entries(modify_u32(dtbo_table(), 16, 257))

    def test_dtbo_trailing_avb_not_authenticated(self):
        report = bridge.inventory(dtbo_table() + b'AVB data not a signature check')
        self.assertIn('not authenticated', report['notes'][0])

    def test_regular_file_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ordinary'
            path.write_bytes(b'abc')
            self.assertEqual(bridge.read_regular(path), b'abc')
            link = Path(tmp) / 'link'
            link.symlink_to(path)
            with self.assertRaises(OSError): bridge.read_regular(link)
            fifo = Path(tmp) / 'pipe'
            os.mkfifo(fifo)
            with self.assertRaises(ValueError): bridge.read_regular(fifo)

    def test_large_file_refused_without_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'big'
            with path.open('wb') as f: f.truncate(bridge.MAX_INPUT + 1)
            with self.assertRaises(ValueError): bridge.read_regular(path)


class CommandTests(unittest.TestCase):
    def test_roundtrip_metadata(self):
        raw = struct.pack('>5BH', 0x39, 0, 2, 1, 70, 3) + b'abc'
        records = bridge.decode_commands(raw)
        self.assertEqual(records[0]['wait_ms'], 70)
        self.assertEqual(records[0]['last'], 0)
        self.assertEqual(bridge.encode_commands(records), raw)

    def test_empty(self):
        with self.assertRaises(ValueError): bridge.decode_commands(b'')

    def test_short_header(self):
        with self.assertRaises(ValueError): bridge.decode_commands(b'123456')

    def test_truncated_payload(self):
        with self.assertRaises(ValueError): bridge.decode_commands(struct.pack('>5BH', 0x39, 1, 0, 0, 0, 4) + b'abc')

    def test_zero_payload(self):
        with self.assertRaises(ValueError): bridge.decode_commands(struct.pack('>5BH', 0x39, 1, 0, 0, 0, 0))

    def test_oversize_payload(self):
        with self.assertRaises(ValueError): bridge.decode_commands(struct.pack('>5BH', 0x39, 1, 0, 0, 0, 4097) + bytes(4097))

    def test_bad_flags(self):
        for pos in (1, 2, 3):
            values = [0x39, 1, 0, 0, 0, 1]
            values[pos] = 9
            with self.subTest(position=pos), self.assertRaises(ValueError):
                bridge.decode_commands(struct.pack('>5BH', *values) + b'a')

    def test_no_sibling_panel_substitution(self):
        with self.assertRaises(ValueError): bridge.panel_data(minimal_fdt())


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.board, cls.driver = apply_subset(Path(cls.tmp.name))
        cls.generated = regen.outputs(ROOT / '.donors', DTC)
        cls.panel = bridge.panel_data(bridge.read_regular(ROOT / '.donors/P85946-qrd-overlay.dtbo'))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_generated_files_exact(self):
        for path, text in self.generated.items():
            with self.subTest(path=str(path)): self.assertEqual(path.read_text(), text)

    def test_donor_regulator_mapping(self):
        facts = json.loads(self.generated[ROOT / 'reference/donor-hardware.json'])
        self.assertEqual(facts['usb_supplies']['/soc/qusb@1613000']['vdd-supply']['name'], ['pm6125_l4'])
        self.assertEqual(facts['usb_supplies']['/soc/qusb@1613000']['vdda18-supply']['name'], ['pm6125_l12'])
        self.assertEqual(facts['usb_supplies']['/soc/qusb@1613000']['vdda33-supply']['name'], ['pm6125_l15'])
        self.assertEqual(facts['sd_supplies']['vdd-supply']['name'], ['pm6125_l22'])
        self.assertEqual(facts['sd_supplies']['vdd-io-supply']['name'], ['pm6125_l5'])

    def test_malformed_donor_voltage_preserved(self):
        facts = json.loads(self.generated[ROOT / 'reference/donor-hardware.json'])
        l15 = facts['usb_supplies']['/soc/qusb@1613000']['vdda33-supply']
        self.assertIsNone(l15['max_uv'])
        self.assertIn('regulator-max-microvolt_raw', l15)
        self.assertTrue(l15['warnings'])

    def test_clock_discrepancy_preserved(self):
        facts = json.loads(self.generated[ROOT / 'reference/donor-hardware.json'])
        self.assertEqual(facts['clocks']['/soc/clocks/sleep_clk'], [32764])
        self.assertIn('clock-frequency = <32764>', self.board)

    def test_correct_source_backed_ids(self):
        self.assertIn('qcom,msm-id = <417 0x10000>, <444 0x10000>;', self.board)
        self.assertIn('qcom,board-id = <0x1000b 0x0>;', self.board)
        self.assertNotIn('qcom,board-id = <0x85943', self.board)

    def test_touch_wiring_unchanged(self):
        self.assertIn('himax,rst-gpio = <&tlmm 31 GPIO_ACTIVE_HIGH>;', self.board)
        self.assertIn('himax,irq-gpio = <&tlmm 80 GPIO_ACTIVE_HIGH>;', self.board)
        self.assertIn('spi-cpha;', self.board)

    def test_firmware_before_alloc(self):
        start = self.driver.index('int himax_chip_common_probe(')
        probe = self.driver[start:]
        self.assertLess(probe.index('himax_select_fw_name(&spi->dev)'), probe.index('gBuffer = kzalloc('))
        self.assertIn('firmware-name = "Himax_firmware_lide_hsd.bin";', self.board)

    def test_exact_panel_sequences(self):
        expected = {'on': 47, 'off': 4, 'diming-off': 2, 'dstb': 6, 'hx83102e-master': 4, 'hx83102e-client': 2, 'panel-status': 2}
        self.assertEqual({k.removeprefix('qcom,mdss-dsi-').removesuffix('-command'): len(v['commands']) for k, v in self.panel['sequences'].items()}, expected)
        for seq in self.panel['sequences'].values():
            self.assertEqual(hashlib.sha256(bridge.encode_commands(seq['commands'])).hexdigest(), seq['sha256'])

    def test_source_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for name in regen.INPUTS:
                shutil.copyfile(ROOT / '.donors' / name, target / name)
            with (target / 'bengal.dtsi').open('a') as f: f.write('\n// changed\n')
            with self.assertRaises(ValueError): regen.outputs(target, DTC)

    def test_all_local_package_checksums(self):
        count = 0
        for port in (PORT, ROOT / 'device/testing/device-samsung-gta4lwifi'):
            text = (port / 'APKBUILD').read_text()
            for digest, name in re.findall(r'^([0-9a-f]{128})  (\S+)$', text, re.M):
                if name.endswith('.tar.gz'): continue
                self.assertEqual(hashlib.sha512((port / name).read_bytes()).hexdigest(), digest, name)
                count += 1
        self.assertEqual(count, 7)

    def test_c_tables_reserialize_exactly(self):
        """Compile the generated C and compare every serialized byte with donor data."""
        source = r'''
#include <stdio.h>
#include "hx83102e_lide_commands.h"
int main(void) {
    for (unsigned i = 0; i < sizeof(gta4l_sequences)/sizeof(gta4l_sequences[0]); ++i) {
        const struct gta4l_dsi_sequence *s = &gta4l_sequences[i];
        for (unsigned j = 0; j < s->count; ++j) {
            const struct gta4l_dsi_cmd *c = &s->commands[j];
            unsigned char h[] = {c->type,c->last,c->channel,c->ack,c->wait_ms,c->size >> 8,c->size & 255};
            if (fwrite(h,1,7,stdout) != 7 || fwrite(c->data,1,c->size,stdout) != c->size) return 1;
        }
    }
    return ferror(stdout) ? 1 : 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            c, binary = Path(tmp) / 'table.c', Path(tmp) / 'table'
            c.write_text(source)
            subprocess.run(['gcc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-pie', '-no-pie', '-I', str(ROOT / 'experimental/panel'), str(c), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True).stdout
            expected = b''.join(bridge.encode_commands(v['commands']) for _, v in sorted(self.panel['sequences'].items()))
            self.assertEqual(result, expected)

    def test_actual_c_firmware_selector(self):
        """Extract the applied function, not a separately reimplemented selector."""
        mocks = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
struct device { bool present; int error; const char *name; };
static char g_fw_name[64];
static bool fallback_ok;
static int device_property_present(struct device *d, const char *p) { (void)p; return d->present; }
static int device_property_read_string(struct device *d, const char *p, const char **out) { (void)p; *out=d->name; return d->error; }
static int dev_err_probe(struct device *d, int e, const char *f) { (void)d; (void)f; return e; }
static long strscpy(char *dst, const char *src, size_t n) {
    size_t len = strlen(src), copy = len < n ? len : n-1;
    memcpy(dst,src,copy); dst[copy]=0; return len < n ? (long)len : -E2BIG;
}
static bool himax_assigned_fw_name(void) {
    if (fallback_ok) strcpy(g_fw_name,"Himax_firmware_lide_hsd.bin");
    return fallback_ok;
}
'''
        cases = r'''
int main(void) {
    struct device d = {true,0,"Himax_firmware_lide_hsd.bin"};
    assert(himax_select_fw_name(&d)==0);
    assert(strcmp(g_fw_name,d.name)==0);
    d.name="other.bin";
    assert(himax_select_fw_name(&d)==0 && strcmp(g_fw_name,"other.bin")==0);
    d.name=""; assert(himax_select_fw_name(&d)==-EINVAL);
    d.error=-ENODATA; assert(himax_select_fw_name(&d)==-ENODATA);
    d.error=-517; assert(himax_select_fw_name(&d)==-517);
    d.error=0;
    char exact[64]; memset(exact,'a',63); exact[63]=0; d.name=exact;
    assert(himax_select_fw_name(&d)==0 && strlen(g_fw_name)==63);
    char big[65]; memset(big,'b',64); big[64]=0; d.name=big;
    assert(himax_select_fw_name(&d)==-ENAMETOOLONG);
    d.present=false; fallback_ok=false;
    assert(himax_select_fw_name(&d)==0 && strcmp(g_fw_name,"Himax_firmware.bin")==0);
    fallback_ok=true;
    for (int i=0;i<10;i++) assert(himax_select_fw_name(&d)==0 && strcmp(g_fw_name,"Himax_firmware_lide_hsd.bin")==0);
    puts("C firmware selection: explicit, repeat, malformed, length, deferred error and fallback cases passed");
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            c, binary = Path(tmp) / 'selector.c', Path(tmp) / 'selector'
            c.write_text(mocks + function_body(self.driver, 'himax_select_fw_name') + cases)
            subprocess.run(['gcc','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-pie','-no-pie',str(c),'-o',str(binary)], check=True)
            subprocess.run([str(binary)], check=True, capture_output=True)

if __name__ == '__main__': unittest.main()
