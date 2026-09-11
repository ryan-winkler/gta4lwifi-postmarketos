#!/usr/bin/env bash
# Build ONLY the target DTB from a verified kernel archive in a fresh temporary tree.
# This does not compile/link the full kernel, install packages, or flash hardware.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
archive=${1:?Usage: bash tools/check-target-dtb.sh VERIFIED_KERNEL_ARCHIVE}
archive=$(realpath "$archive")
[[ -f "$archive" && ! -L "$archive" ]] || exit 2
expected='2a6393212c413cf3812c2293d074fc9b7f82dec01c740251fe390b0633484b247e95e886493cbec77e6ef9741aebe0a4134c2218672424b332ae119c22566f23'
printf '%s  %s\n' "$expected" "$archive" | sha512sum --check -
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
# Extract the verified archive with Python's data filter; kernel sources contain legitimate symlinks.
python3 - "$archive" "$work" <<'PY'
import pathlib, sys, tarfile
with tarfile.open(sys.argv[1], 'r:gz') as tar:
    members = tar.getmembers()
    for m in members:
        p = pathlib.PurePosixPath(m.name)
        if p.is_absolute() or '..' in p.parts or not (m.isfile() or m.isdir() or m.issym() or m.islnk()):
            raise SystemExit('Unsupported or unsafe archive entry: ' + m.name)
    tar.extractall(sys.argv[2], members=members, filter='data')
PY
kernel="$work/linux"
[[ -f "$kernel/Makefile" ]] || { echo 'Unexpected source archive layout' >&2; exit 2; }
port="$repo/device/testing/linux-postmarketos-qcom-sm6115"
cd "$kernel"
git init -q
for p in "$port"/000[1-4]-*.patch; do
  git apply --check "$p"
  git apply "$p"
done
cp "$port/config-postmarketos-qcom-sm6115.aarch64" .config
make ARCH=arm64 LLVM=1 olddefconfig
make ARCH=arm64 LLVM=1 -j2 qcom/sm6115-samsung-gta4lwifi.dtb
mkdir -p "$repo/evidence"
cp arch/arm64/boot/dts/qcom/sm6115-samsung-gta4lwifi.dtb "$repo/evidence/target-board.dtb"
cp .config "$repo/evidence/target-resolved.config"
python3 "$repo/tools/donor_bridge.py" inspect "$repo/evidence/target-board.dtb" > "$repo/evidence/target-dtb-inventory.json"
printf '%s\n' 'Full source patch application and target DTB build passed; this is NOT a full kernel build.'
