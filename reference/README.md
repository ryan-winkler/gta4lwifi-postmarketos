# Reproducible donor hardware facts

Run `python3 tools/regenerate_donor.py --write` after fetching the pinned donor
sources. This creates `donor-hardware.json` and the experimental panel header.
Both are published in CI artifacts and included in the worked-files bundle.

The generator validates Git blob identities for the complete donor inputs,
compiles them with DTC, resolves supply references and records source anomalies.
No firmware binary, host credentials or live tablet data are included.

The donor's 32,764 Hz sleep-clock declaration and malformed L15 maximum voltage
are preserved explicitly. Neither is represented as a physical measurement.
