# Exact Lide HSD panel data

Run `python3 tools/fetch_donors.py` and
`python3 tools/regenerate_donor.py --write` from the repository root.
The generated `hx83102e_lide_commands.h` contains the seven exact donor command
sequences (67 records), including transport flags and waits. CI publishes it as
an artifact. The verifier compiles a C round-trip test against the donor bytes.

This is data for the native panel implementation, not an enabled panel driver.
Power sequencing, GPIO ownership, DSI batching, brightness and lifecycle still
need integration. See `docs/DONOR-INTEGRATION.md`.
