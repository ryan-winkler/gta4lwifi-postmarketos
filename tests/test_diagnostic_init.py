"""Validate diagnostic archive structure; hardware execution is a separate gate."""
import gzip
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from test_donor_bridge import ROOT
sys.path.insert(0, str(ROOT / 'tools'))
from build_diag_initramfs import newc, verify_elf


def unpack(data):
    entries, pos = {}, 0
    while True:
        if data[pos:pos+6] != b'070701':
            raise AssertionError('Invalid newc magic')
        fields = [int(data[pos+6+i*8:pos+14+i*8],16) for i in range(13)]
        pos += 110
        ino, mode, uid, gid, nlink, mtime, size, dmaj, dmin, rmaj, rmin, nsize, check = fields
        name = data[pos:pos+nsize]
        if not name.endswith(b'\0'):
            raise AssertionError('Invalid name termination')
        pos = (pos+nsize+3)//4*4
        content = data[pos:pos+size]
        pos = (pos+size+3)//4*4
        if name == b'TRAILER!!!\0':
            return entries
        entries[name[:-1].decode()] = (mode, uid, gid, rmaj, rmin, content)


class DiagnosticTests(unittest.TestCase):
    def test_console_device_and_executable_modes(self):
        archive = newc([('dev', 0o040755, b'', 0, 0), ('dev/console', 0o020600, b'', 5, 1),
                        ('init', 0o100755, b'payload', 0, 0)])
        entries = unpack(archive)
        self.assertEqual(entries['dev/console'][:5], (0o020600,0,0,5,1))
        self.assertEqual(entries['init'], (0o100755,0,0,0,0,b'payload'))

    def test_archive_is_deterministic(self):
        entries = [('init', 0o100755, b'payload', 0, 0)]
        self.assertEqual(newc(entries), newc(entries))
        self.assertEqual(gzip.compress(newc(entries), mtime=0), gzip.compress(newc(entries), mtime=0))

    def test_non_arm64_is_rejected(self):
        with self.assertRaises(ValueError): verify_elf(b'not executable')

    def test_interpreter_is_rejected(self):
        elf = bytearray(120);elf[:6]=b'\x7fELF\x02\x01'
        struct.pack_into('<HH',elf,16,2,183);struct.pack_into('<Q',elf,32,64)
        struct.pack_into('<HH',elf,54,56,1);struct.pack_into('<I',elf,64,3)
        with self.assertRaises(ValueError): verify_elf(bytes(elf))
