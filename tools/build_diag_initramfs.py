#!/usr/bin/env python3
"""Build a static AArch64 diagnostic cpio; never package or flash BOOT implicitly."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys


def newc(entries: list[tuple[str, int, bytes, int, int]]) -> bytes:
    result = bytearray()
    for ino, (name, mode, data, major, minor) in enumerate(entries + [('TRAILER!!!', 0, b'', 0, 0)], 1):
        encoded = name.encode() + b'\0'
        fields = (ino, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0)
        result += b'070701' + ''.join(f'{n:08x}' for n in fields).encode() + encoded
        result += bytes((-len(result)) % 4)
        result += data
        result += bytes((-len(result)) % 4)
    return bytes(result)


def verify_elf(data: bytes) -> None:
    if (len(data) < 64 or data[:6] != b'\x7fELF\x02\x01'
            or struct.unpack_from('<HH', data, 16) != (2, 183)):
        raise ValueError('Expected static AArch64 little-endian ELF executable')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    if size != 56 or count < 1 or offset + size * count > len(data):
        raise ValueError('Invalid ELF program-header table')
    for i in range(count):
        if struct.unpack_from('<I', data, offset + i * size)[0] in (2, 3):
            raise ValueError('Dynamic/interpreter ELF is not standalone')


def build(output: Path, cc: str) -> dict:
    # Preserve existing candidates. Keep every generated file in a fresh directory.
    output.mkdir(parents=False, exist_ok=False)
    source = Path(__file__).resolve().parents[1] / 'diagnostics/init.c'
    executable = output / 'init'
    command = [cc, '--target=aarch64-linux-gnu', '-fuse-ld=lld', '-nostdlib', '-static',
               '-fno-stack-protector', '-fno-builtin', '-fno-pie', '-O2', '-Wall', '-Wextra',
               '-Werror', '-Wl,-e,_start', '-Wl,--build-id=none', str(source), '-o', str(executable)]
    subprocess.run(command, check=True, timeout=60)
    elf = executable.read_bytes()
    verify_elf(elf)
    entries = [('dev', 0o040755, b'', 0, 0), ('proc', 0o040755, b'', 0, 0),
               ('sys', 0o040755, b'', 0, 0), ('dev/console', 0o020600, b'', 5, 1),
               ('dev/null', 0o020666, b'', 1, 3), ('init', 0o100755, elf, 0, 0)]
    ramdisk = output / 'diagnostic-initramfs.cpio.gz'
    ramdisk.write_bytes(gzip.compress(newc(entries), mtime=0))
    report = {'command': command, 'compiler': subprocess.check_output([cc, '--version'], text=True),
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'files': {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in (executable, ramdisk)},
              'hardware_verified': False, 'flash_approved': False,
              'purpose': 'Static PID1 boot-stage marker, not postmarketOS or a Plasma installation'}
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path, help='New directory; parent must already exist')
    p.add_argument('--cc', default='clang')
    args = p.parse_args()
    try:
        print(json.dumps(build(args.output, args.cc), indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
