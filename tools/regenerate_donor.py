#!/usr/bin/env python3
"""Regenerate pinned donor facts and C command tables; default is comparison only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from donor_bridge import read_regular, panel_data, render_header, cells, DONOR_COMMIT
from fdt_reader import fdt_nodes

ROOT = Path(__file__).resolve().parents[1]
INPUTS = {'bengal.dtsi': 'a397c0d6848c873b95de36f81fe11122bd1c148f',
          'P85946-qrd-overlay.dts': '9f8e83cb2745b0c3f050d132c17f66ebaee92bef'}


def regulator(nodes: dict, phandle: list[int]) -> dict:
    matches = [(p, v) for p, v in nodes.items() if cells(v, 'phandle') == phandle]
    if len(matches) != 1:
        raise ValueError('Unresolved or ambiguous regulator phandle')
    path, props = matches[0]
    result = dict(path=path, name=props.get('regulator-name', {}).get('strings'))
    for label, prop in [('min_uv', 'regulator-min-microvolt'), ('max_uv', 'regulator-max-microvolt')]:
        raw = props.get(prop)
        # The donor's L15 maximum is a three-byte string, not a u32. Preserve
        # that defect instead of guessing a voltage or hiding source drift.
        valid = raw is not None and raw.get('byte_length') == 4
        result[label] = raw['u32_cells'][0] if valid else None
        if raw is not None and not valid:
            result[prop + '_raw'] = raw
            result.setdefault('warnings', []).append(prop + ' is not one u32; not translated')
    return result


def outputs(source_dir: Path, dtc: str) -> dict[Path, str]:
    source_records = []
    for name, expected in INPUTS.items():
        data = read_regular(source_dir / name)
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if blob != expected:
            raise ValueError(f'Pinned donor identity mismatch: {name}')
        source_records.append(dict(file=name, git_blob=blob, sha256=hashlib.sha256(data).hexdigest()))
    with tempfile.TemporaryDirectory() as tmp:
        blobs = []
        for name in INPUTS:
            output = Path(tmp) / (name + '.dtb')
            subprocess.run([dtc, '-q', '-I', 'dts', '-O', 'dtb', '-o', str(output), str(source_dir / name)], check=True, timeout=60)
            blobs.append(read_regular(output))
    base, overlay = map(fdt_nodes, blobs)
    panel = panel_data(blobs[1])
    panel['source_identity_verified'] = True
    facts = dict(reference_commit=DONOR_COMMIT, source_records=source_records,
                 msm_id=cells(base['/'], 'qcom,msm-id'), base_board_id=cells(base['/'], 'qcom,board-id'),
                 overlay_board_id=cells(overlay['/'], 'qcom,board-id'),
                 clocks={p: cells(base[p], 'clock-frequency') for p in ['/soc/clocks/xo_board', '/soc/clocks/sleep_clk']},
                 usb_supplies={}, sd_supplies={}, panel_node=panel['source_node'],
                 panel_properties=panel['panel_properties'],
                 panel_supply_reference_nodes=panel['supply_reference_nodes'],
                 panel_sequences={k: dict(bytes=v['bytes'], sha256=v['sha256'], records=len(v['commands']), state=v['state']) for k, v in panel['sequences'].items()},
                 hardware_verified=False,
                 interpretation='Published donor declarations, not live measurements. Numeric board ID is the overlay selector; never derive it from androidboot.board_id.')
    for path, properties in {'/soc/qusb@1613000': ['vdd-supply', 'vdda18-supply', 'vdda33-supply'],
                             '/soc/ssphy@1615000': ['vdd-supply', 'core-supply']}.items():
        facts['usb_supplies'][path] = {name: regulator(base, cells(base[path], name)) for name in properties}
    # Resolve external overlay fixups through the base symbols, not numeric placeholders.
    sd = '/fragment@48/__overlay__'
    for prop in ('vdd-supply', 'vdd-io-supply', 'vdd-io-bias-supply'):
        fixup = sd + ':' + prop + ':0'
        names = [name for name, value in overlay['/__fixups__'].items() if fixup in value.get('strings', [])]
        if len(names) != 1:
            raise ValueError('Missing or ambiguous SD supply fixup')
        path = base['/__symbols__'][names[0]]['strings'][0]
        facts['sd_supplies'][prop] = regulator(base, cells(base[path], 'phandle'))
    facts['timing_properties'] = {k: v for k, v in panel['timing_properties'].items() if not k.endswith('-command')}
    return {ROOT / 'reference/donor-hardware.json': json.dumps(facts, indent=2) + '\n',
            ROOT / 'experimental/panel/hx83102e_lide_commands.h': render_header(panel)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources', type=Path, default=ROOT / '.donors'); p.add_argument('--dtc', default='dtc')
    p.add_argument('--write', action='store_true', help='Explicitly update the two generated project files')
    args = p.parse_args()
    try:
        generated = outputs(args.sources, args.dtc)
        for path, text in generated.items():
            if args.write:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            elif not path.is_file() or path.read_text() != text:
                raise ValueError(f'Generated file drift: {path.relative_to(ROOT)}')
            print(('WROTE ' if args.write else 'MATCH ') + str(path.relative_to(ROOT)))
        return 0
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
