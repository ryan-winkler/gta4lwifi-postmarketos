#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p evidence
# Compile data only. Neither source is executed or installed on hardware.
dtc -q -I dts -O dtb -o .donors/bengal.dtb .donors/bengal.dtsi
dtc -q -I dts -O dtb -o .donors/P85946-qrd-overlay.dtbo .donors/P85946-qrd-overlay.dts
# Preserve the independent compiler for the offline review environment.
mkdir -p .donors/review-tools
cp /usr/bin/dtc .donors/review-tools/dtc
dtc --version | tee evidence/dtc-version.txt
if test -f tests/test_donor_bridge.py; then
  python3 -m unittest discover -s tests -v 2>&1 | tee evidence/tests.txt
fi
