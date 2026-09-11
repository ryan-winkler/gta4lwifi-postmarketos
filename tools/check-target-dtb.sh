#!/usr/bin/env bash
# Build the target DTB and selected Himax driver objects from a verified archive.
# This does not link the full kernel, install packages, or flash hardware.
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
# Compile the real driver against the target headers, not just mocked host APIs.
make ARCH=arm64 LLVM=1 -j2 drivers/input/touchscreen/hxchipset/
mkdir -p "$repo/evidence"
find drivers/input/touchscreen/hxchipset -name "*.o" -type f -exec sha256sum {} + > "$repo/evidence/target-driver-object-hashes.txt"
test -s "$repo/evidence/target-driver-object-hashes.txt"
cp arch/arm64/boot/dts/qcom/sm6115-samsung-gta4lwifi.dtb "$repo/evidence/target-board.dtb"
cp .config "$repo/evidence/target-resolved.config"
python3 "$repo/tools/donor_bridge.py" inspect "$repo/evidence/target-board.dtb" > "$repo/evidence/target-dtb-inventory.json"
printf '%s\n' 'Full patch application, target DTB and selected Himax object compilation passed; this is NOT a full kernel link.'
