#!/usr/bin/env python3
"""Bounded FDT v17 reader, retained from the project's QA/CSO-reviewed inspector.

No image code is executed. Unknown/ambiguous structures fail explicitly.
"""
from __future__ import annotations
import struct

def align(n: int, size: int) -> int:
    return (n + size - 1) // size * size

def fdt_nodes(data: bytes) -> dict:
    """Parse a bounded, single version-17 DTB without collapsing duplicate entries."""
    if len(data) < 40:
        raise ValueError('Truncated FDT header')
    h = struct.unpack_from('>10I', data)
    magic, total, so, stro, reserve, version, compat, _, string_size, struct_size = h
    if magic != 0xd00dfeed or total != len(data) or not 40 <= total <= 16 * 1024 * 1024:
        raise ValueError('Invalid FDT magic or totalsize')
    if version != 17 or compat > 17:
        raise ValueError('Only FDT version 17 is supported by this inspector')
    if so < 40 or so % 4 or reserve < 40 or reserve % 8 or not struct_size:
        raise ValueError('Invalid FDT block offset/alignment')
    if stro < 40 or stro + string_size > total or so + struct_size > total:
        raise ValueError('FDT blocks outside totalsize')
    ro = reserve
    while ro + 16 <= total:
        pair = struct.unpack_from('>QQ', data, ro); ro += 16
        if pair == (0, 0): break
    else:
        raise ValueError('Unterminated FDT reservation map')
    ranges = sorted([(0, 40), (reserve, ro), (so, so + struct_size), (stro, stro + string_size)])
    for before, after in zip(ranges, ranges[1:]):
        if before[1] > after[0]: raise ValueError('Overlapping FDT blocks')
    strings = data[stro:stro + string_size]
    off, end, stack, nodes, child_seen = so, so + struct_size, [], {}, {}
    property_count = 0
    while off + 4 <= end:
        token = struct.unpack_from('>I', data, off)[0]; off += 4
        if token == 1:
            stop = data.find(b'\0', off, end)
            if stop < 0: raise ValueError('Unterminated FDT node')
            name = data[off:stop].decode('ascii')
            if not stack:
                if nodes or name: raise ValueError('Invalid or multiple FDT roots')
            elif not name or '/' in name or any(ord(c) < 33 or ord(c) > 126 for c in name):
                raise ValueError('Invalid FDT node name')
            if stack: child_seen['/' + '/'.join(n for n in stack if n)] = True
            stack.append(name)
            if len(stack) > 128 or len(nodes) >= 100000: raise ValueError('FDT complexity limit exceeded')
            path = '/' + '/'.join(n for n in stack if n)
            if path in nodes: raise ValueError('Duplicate FDT node')
            nodes[path] = {}; child_seen[path] = False
            off = align(stop + 1, 4)
            if off > end: raise ValueError('FDT node padding out of bounds')
        elif token == 2:
            if not stack: raise ValueError('Unbalanced FDT node stack')
            stack.pop()
        elif token == 3:
            if not stack or off + 8 > end: raise ValueError('Invalid FDT property')
            length, noff = struct.unpack_from('>II', data, off); off += 8
            if noff >= len(strings) or off + length > end or length > 1024 * 1024:
                raise ValueError('FDT property out of bounds or too large')
            name_end = strings.find(b'\0', noff)
            if name_end < 0: raise ValueError('Unterminated property name')
            name = strings[noff:name_end].decode('ascii')
            if not name or '/' in name or any(ord(c) < 33 or ord(c) > 126 for c in name):
                raise ValueError('Invalid FDT property name')
            path = '/' + '/'.join(n for n in stack if n)
            if name in nodes[path]: raise ValueError('Duplicate FDT property')
            if child_seen[path]: raise ValueError('FDT property follows child nodes')
            property_count += 1
            if property_count > 100000: raise ValueError('FDT property limit exceeded')
            raw = data[off:off + length]; off = align(off + length, 4)
            if off > end: raise ValueError('FDT property padding out of bounds')
            value = {'hex': raw.hex(), 'byte_length': len(raw)}
            if not raw: value['boolean'] = True
            if raw and len(raw) % 4 == 0:
                value['u32_cells'] = list(struct.unpack('>' + 'I' * (len(raw) // 4), raw))
            if raw.endswith(b'\0'):
                parts = raw[:-1].split(b'\0')
                if all(p and all(32 <= c < 127 for c in p) for p in parts):
                    value['strings'] = [p.decode('ascii') for p in parts]
            nodes[path][name] = value
        elif token == 4:
            pass
        elif token == 9:
            if stack or '/' not in nodes: raise ValueError('Invalid FDT end/root')
            if off != end: raise ValueError('Unparsed data after FDT end token')
            return nodes
        else:
            raise ValueError(f'Unexpected FDT token {token}')
    raise ValueError('Missing FDT end token')

