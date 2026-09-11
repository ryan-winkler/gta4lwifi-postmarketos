#!/usr/bin/env python3
"""Inspect boot/DTBO containers and translate the exact Lide panel command data.

Read-only inputs, bounded parsing, no flash/mount/shell execution. Generated
panel tables are porting inputs, not an enabled or hardware-tested panel driver.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import zlib
from fdt_reader import align, fdt_nodes

MAX_INPUT = 128 * 1024 * 1024
MAX_UNPACKED = 512 * 1024 * 1024
PANEL = '/fragment@23/__overlay__/qcom,mdss_dsi_hx83102e_lide_hsd_video'
DONOR_COMMIT = 'c058c8a0930d4352eaa96a172f83515077e9ea62'


def read_regular(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT:
            raise ValueError('Input must be a bounded regular file, not a device')
        data = stream.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise ValueError('Input exceeds limit')
        return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fdt_series(data: bytes) -> list[bytes]:
    """Read concatenated trees by totalsize; never scan arbitrary bytes for magic."""
    result, pos = [], 0
    while pos < len(data):
        if not any(data[pos:]):  # Explicit trailing partition padding only.
            break
        if len(result) >= 256 or pos + 40 > len(data):
            raise ValueError('Truncated or excessive concatenated FDTs')
        magic, size = struct.unpack_from('>II', data, pos)
        if magic != 0xd00dfeed or not 40 <= size <= len(data) - pos:
            raise ValueError('Invalid FDT boundary; blind magic scanning is forbidden')
        blob = data[pos:pos + size]
        fdt_nodes(blob)
        result.append(blob)
        pos += size
    if not result:
        raise ValueError('No device trees in supplied section')
    return result


def dtbo_entries(data: bytes) -> list[dict]:
    if len(data) < 32:
        raise ValueError('Truncated DTBO table header')
    magic, total, hsz, esz, count, eoff, page, version = struct.unpack_from('>8I', data)
    if magic != 0xd7b7ab1e or version != 0:
        raise ValueError('Only uncompressed Android DT table version 0 is supported')
    if not (32 <= hsz <= eoff <= total <= len(data)) or esz != 32:
        raise ValueError('Invalid DTBO header/entry sizes')
    if not 1 <= count <= 256 or eoff + count * esz > total:
        raise ValueError('Invalid DTBO entry count or table boundary')
    if page == 0 or page & (page - 1):
        raise ValueError('Invalid DTBO page size')
    result, ranges = [], []
    end_table = eoff + count * esz
    for index in range(count):
        size, offset, ident, revision, *custom = struct.unpack_from('>8I', data, eoff + index * esz)
        if size < 40 or offset < end_table or offset + size > total:
            raise ValueError('DTBO entry outside payload')
        # Identical shared entries are valid; partial overlap is ambiguous.
        span = (offset, offset + size)
        for other in ranges:
            if span != other and max(span[0], other[0]) < min(span[1], other[1]):
                raise ValueError('Partially overlapping DTBO entries')
        ranges.append(span)
        blob = data[offset:offset + size]
        fdt_nodes(blob)
        result.append(dict(index=index, id=ident, revision=revision, custom=custom,
                           offset=offset, size=size, blob=blob))
    return result


def boot_sections(data: bytes) -> tuple[dict, dict[str, bytes]]:
    if len(data) < 1632 or data[:8] != b'ANDROID!':
        raise ValueError('Not an Android v0-v2 boot image')
    keys = ['kernel_size', 'kernel_addr', 'ramdisk_size', 'ramdisk_addr',
            'second_size', 'second_addr', 'tags_addr', 'page_size', 'header_version', 'os_version']
    h = dict(zip(keys, struct.unpack_from('<10I', data, 8)))
    version, page = h['header_version'], h['page_size']
    if version not in (0, 1, 2) or not 2048 <= page <= 65536 or page & (page - 1):
        raise ValueError('Unsupported Android boot header or page size')
    if len(data) < page:
        raise ValueError('Truncated boot header page')
    if version:
        h.update(zip(['recovery_dtbo_size', 'recovery_dtbo_offset', 'header_size'], struct.unpack_from('<IQI', data, 1632)))
        if h['header_size'] != (1648 if version == 1 else 1660):
            raise ValueError('Incorrect Android boot header_size')
    if version == 2:
        h.update(zip(['dtb_size', 'dtb_addr'], struct.unpack_from('<IQ', data, 1648)))
    h['cmdline'] = (data[64:576].split(b'\0', 1)[0] + data[608:1632].split(b'\0', 1)[0]).decode('utf-8', 'replace')
    pos, sections = page, {}
    for name in ('kernel', 'ramdisk', 'second', 'recovery_dtbo', 'dtb'):
        size = h.get(name + '_size', 0)
        if size and (pos + size > len(data) or align(pos + size, page) > len(data)):
            raise ValueError(f'Truncated boot {name}')
        if name == 'recovery_dtbo' and size and h['recovery_dtbo_offset'] != pos:
            raise ValueError('Recovery DTBO offset does not match component layout')
        sections[name] = data[pos:pos + size]
        pos += align(size, page)
    if not sections['kernel']:
        raise ValueError('Empty kernel')
    return h, sections


def cells(node: dict, name: str) -> list[int] | None:
    prop = node.get(name)
    if prop is None:
        return None
    if 'u32_cells' not in prop:
        raise ValueError(f'{name} is not an array of 32-bit cells')
    return prop['u32_cells']


def summarize(blob: bytes, role: str, **metadata) -> dict:
    nodes = fdt_nodes(blob)
    root = nodes['/']
    clocks = {path: cells(props, 'clock-frequency') for path, props in nodes.items()
              if 'fixed-clock' in props.get('compatible', {}).get('strings', [])}
    return dict(role=role, sha256=sha256(blob), size=len(blob),
                msm_id=cells(root, 'qcom,msm-id'), board_id=cells(root, 'qcom,board-id'),
                fixed_clocks=clocks, **metadata)


def inventory(data: bytes) -> dict:
    trees, header, notes = [], None, []
    if data[:8] == b'ANDROID!':
        header, sections = boot_sections(data)
        if sections['dtb']:
            trees += [summarize(b, 'header-dtb', index=i) for i, b in enumerate(fdt_series(sections['dtb']))]
        else:
            notes.append('No separate header DTB section')
        kernel = sections['kernel']
        if kernel.startswith(b'\x1f\x8b'):
            dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
            payload = dec.decompress(kernel, MAX_UNPACKED + 1)
            if len(payload) > MAX_UNPACKED or not dec.eof:
                raise ValueError('Truncated gzip kernel or decompression limit exceeded')
            if dec.unused_data and any(dec.unused_data):
                trees += [summarize(b, 'appended-dtb', index=i) for i, b in enumerate(fdt_series(dec.unused_data))]
            else:
                notes.append('No DTBs after the gzip kernel member; compressed-internal trees are not inferred')
        else:
            notes.append('Non-gzip kernel: appended DTBs not inspected; use a verified payload boundary')
        if sections['recovery_dtbo']:
            for entry in dtbo_entries(sections['recovery_dtbo']):
                blob = entry.pop('blob')
                entry.pop('size')
                trees.append(summarize(blob, 'recovery-dtbo', **entry))
        fmt = 'android-boot'
    elif data[:4] == b'\xd7\xb7\xab\x1e':
        for entry in dtbo_entries(data):
            blob = entry.pop('blob')
            entry.pop('size')
            trees.append(summarize(blob, 'dtbo', **entry))
        fmt = 'dtbo-table-v0'
        notes.append('Container entries checked; any trailing AVB metadata/signature is not authenticated')
    else:
        trees = [summarize(b, 'raw-dtb', index=i) for i, b in enumerate(fdt_series(data))]
        fmt = 'fdt-series'
    return dict(format=fmt, sha256=sha256(data), header=header, trees=trees, notes=notes,
                hardware_verified=False)


def decode_commands(data: bytes) -> list[dict]:
    """Decode Qualcomm 7-byte DSI records without discarding transport metadata."""
    pos, commands = 0, []
    if not data or len(data) > 65536:
        raise ValueError('Empty or oversized command sequence')
    while pos < len(data):
        if pos + 7 > len(data) or len(commands) >= 1024:
            raise ValueError('Truncated command header or too many commands')
        dtype, last, vc, ack, delay, size = struct.unpack_from('>5BH', data, pos)
        pos += 7
        if last not in (0, 1) or ack not in (0, 1) or vc > 3:
            raise ValueError('Invalid command flags/channel')
        if not 1 <= size <= 4096 or pos + size > len(data):
            raise ValueError('Invalid or truncated command payload')
        commands.append(dict(type=dtype, last=last, channel=vc, ack=ack,
                             wait_ms=delay, payload=data[pos:pos + size].hex()))
        pos += size
    return commands


def encode_commands(commands: list[dict]) -> bytes:
    return b''.join(struct.pack('>5BH', c['type'], c['last'], c['channel'], c['ack'],
                                c['wait_ms'], len(bytes.fromhex(c['payload']))) + bytes.fromhex(c['payload'])
                    for c in commands)


def panel_data(blob: bytes) -> dict:
    nodes = fdt_nodes(blob)
    if PANEL not in nodes:
        raise ValueError('Exact HX83102E Lide HSD panel node is absent; no sibling substitution')
    panel, timing = nodes[PANEL], nodes[PANEL + '/qcom,mdss-dsi-display-timings/timing@0']
    sequences = {}
    for owner in (panel, timing):
        for name, prop in owner.items():
            if name.endswith('-command'):
                raw = bytes.fromhex(prop['hex'])
                commands = decode_commands(raw)
                if encode_commands(commands) != raw:
                    raise ValueError('Command round-trip changed donor bytes')
                sequences[name] = dict(sha256=sha256(raw), bytes=len(raw), commands=commands,
                                      state=owner.get(name + '-state', {}).get('strings'))
    supplies = cells(panel, 'qcom,panel-supply-entries')
    supply_nodes = {}
    if supplies:
        for path, props in nodes.items():
            if cells(props, 'phandle') == supplies:
                supply_nodes = {p: v for p, v in nodes.items() if p == path or p.startswith(path + '/')}
                break
    return dict(reference_commit=DONOR_COMMIT, source_identity_verified=False, source_node=PANEL, source_dtb_sha256=sha256(blob),
                panel_properties=panel, timing_properties=timing, supply_reference_nodes=supply_nodes,
                sequences=sequences, hardware_verified=False,
                limitations=['GPIO placeholders require overlay fixup resolution',
                             'These tables do not implement regulators, host clocks, panel lifecycle or KWin',
                             'Vendor last-command batching has no automatic generic mainline equivalent'])


def render_header(panel: dict) -> str:
    """Portable data tables; no implicit MMIO/GPIO/DSI operations."""
    origin = ('Pinned Samsung/Ubuntu Touch donor: ' + DONOR_COMMIT) if panel.get('source_identity_verified') else 'Unverified source input; validate provenance before use'
    lines = ['/* SPDX-License-Identifier: GPL-2.0-only */', '/* ' + origin + ' */',
             '/* Data only: not an enabled panel driver. See docs/DONOR-INTEGRATION.md. */',
             '#ifndef GTA4L_LIDE_COMMANDS_H', '#define GTA4L_LIDE_COMMANDS_H',
             'struct gta4l_dsi_cmd { unsigned char type, last, channel, ack, wait_ms; unsigned short size; const unsigned char *data; };']
    for index, (name, sequence) in enumerate(sorted(panel['sequences'].items())):
        ident = 'gta4l_' + name.removeprefix('qcom,mdss-dsi-').removesuffix('-command').replace('-', '_')
        lines.append(f'/* {name}; state: {sequence["state"]} */')
        for j, command in enumerate(sequence['commands']):
            payload = bytes.fromhex(command['payload'])
            lines.append(f'static const unsigned char {ident}_{j}[] = {{' + ','.join(f'0x{x:02x}' for x in payload) + '};')
        lines.append(f'static const struct gta4l_dsi_cmd {ident}[] = {{')
        for j, c in enumerate(sequence['commands']):
            lines.append('  {' + ','.join(str(c[k]) for k in ('type', 'last', 'channel', 'ack', 'wait_ms')) + f', sizeof({ident}_{j}), {ident}_{j}' + '},')
        lines.append('};')
    lines += ['struct gta4l_dsi_sequence { const char *name; unsigned count; const struct gta4l_dsi_cmd *commands; };', 'static const struct gta4l_dsi_sequence gta4l_sequences[] = {']
    for name, sequence in sorted(panel['sequences'].items()):
        ident = 'gta4l_' + name.removeprefix('qcom,mdss-dsi-').removesuffix('-command').replace('-', '_')
        lines.append(f'  {{"{name}", {len(sequence["commands"])}, {ident}}},')
    lines += ['};', '#endif', '']
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('inspect').add_argument('image', type=Path)
    p = sub.add_parser('panel'); p.add_argument('overlay', type=Path); p.add_argument('--header', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            result = inventory(read_regular(args.image))
        else:
            result = panel_data(read_regular(args.overlay))
            if args.header:
                print(render_header(result), end='')
                return 0
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError, struct.error, zlib.error, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
