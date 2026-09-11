#!/usr/bin/env python3
"""Download two public, commit-pinned source files; verify before caching. No execution."""
from pathlib import Path
import hashlib
import os
import sys
import urllib.request
from regenerate_donor import INPUTS
from donor_bridge import DONOR_COMMIT, read_regular

ROOT = Path(__file__).resolve().parents[1]
REPO = 'jojobear691/kernel-samsung-sm6115-halium12'


def identity(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def main():
    target = ROOT / '.donors'
    if target.is_symlink():
        raise ValueError('Refusing symlinked donor cache')
    target.mkdir(exist_ok=True)
    for name, expected in INPUTS.items():
        dest = target / name
        if dest.exists() or dest.is_symlink():
            data = read_regular(dest)
        else:
            url = f'https://raw.githubusercontent.com/{REPO}/{DONOR_COMMIT}/arch/arm64/boot/dts/vendor/qcom/{name}'
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024 or identity(data) != expected:
                raise ValueError('Invalid downloaded source: ' + name)
            fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
        if identity(data) != expected:
            raise ValueError('Cached source drift; existing file preserved: ' + name)
        print('VERIFIED ' + name + ' ' + expected)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        raise SystemExit(2)
