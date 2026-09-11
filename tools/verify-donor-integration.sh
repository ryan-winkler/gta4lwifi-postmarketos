#!/usr/bin/env bash
# Source/host verification only. No root, flashing, mounting, or device access.
set -euo pipefail
cd "$(dirname "$0")/.."
export DTC="${DTC:-dtc}"
for tool in python3 gcc git "$DTC"; do command -v "$tool" >/dev/null; done
if [[ -L evidence ]]; then echo 'Refusing symlinked evidence directory' >&2; exit 2; fi
mkdir -p evidence
# Fetching is explicit: use tools/fetch_donors.py first on a fresh checkout.
"$DTC" -q -I dts -O dtb -o .donors/bengal.dtb .donors/bengal.dtsi
"$DTC" -q -I dts -O dtb -o .donors/P85946-qrd-overlay.dtbo .donors/P85946-qrd-overlay.dts
"$DTC" --version | tee evidence/dtc-version.txt
python3 tools/regenerate_donor.py --dtc "$DTC"
sh -n device/testing/device-samsung-gta4lwifi/APKBUILD
sh -n device/testing/device-samsung-gta4lwifi/deviceinfo
sh -n device/testing/linux-postmarketos-qcom-sm6115/APKBUILD
python3 -m unittest discover -s tests -v 2>&1 | tee evidence/tests.txt
printf '%s\n' 'Source, focused C, and container checks passed. Full kernel/abuild and all hardware gates remain separate.'
