#!/usr/bin/env python3
"""Read this overlay's literal APKBUILD patch list without executing shell code."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
import sys


def patch_paths(port: Path) -> list[Path]:
    text = (port / 'APKBUILD').read_text()
    block = re.findall(r'^source="([^"\n]*(?:\n[^"\n]*)*)"', text, re.M)
    sums = re.findall(r'^sha512sums="([^"\n]*(?:\n[^"\n]*)*)"', text, re.M)
    if len(block) != 1 or len(sums) != 1:
        raise ValueError('Expected one literal source and sha512sums block')
    entries = block[0].split()
    names = [entry for entry in entries if '.patch' in entry]
    if not names or len(names) != len(set(names)):
        raise ValueError('Empty or duplicate patch list')
    expected = {}
    for line in sums[0].splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 2 or not re.fullmatch(r'[0-9a-f]{128}', fields[0]):
            raise ValueError('Malformed SHA-512 entry')
        digest, name = fields
        if name in expected:
            raise ValueError('Duplicate checksum entry')
        expected[name] = digest
    paths = []
    for name in names:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.patch', name):
            raise ValueError('Only literal local patch names are supported')
        path = port / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Patch is not a regular local file: ' + name)
        if hashlib.sha512(path.read_bytes()).hexdigest() != expected.get(name):
            raise ValueError('Patch checksum mismatch: ' + name)
        paths.append(path.resolve())
    if set(names) != {p.name for p in port.glob('*.patch')}:
        raise ValueError('APKBUILD and on-disk patch list differ')
    return paths


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('port', type=Path)
    args = p.parse_args()
    try:
        print('\n'.join(str(path) for path in patch_paths(args.port)))
        return 0
    except (ValueError, OSError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
