# gta4lwifi postmarketOS port

Device and kernel package overlay for the Samsung Galaxy Tab A7 10.4 (2020)
Wi-Fi, SM-T500 (`samsung-gta4lwifi`). This is **not a complete pmaports checkout**
and is **not a hardware-validated installation**.

## Layout

- `device/testing/device-samsung-gta4lwifi/`: device package and boot metadata.
- `device/testing/linux-postmarketos-qcom-sm6115/`: near-mainline kernel package.
  - `0001`: board description, original configuration and battery ID addition.
  - `0002`: Samsung-derived HX83102 SPI import and GPIO/API conversion.
  - `0003`: follow-up PM, resource-error, DMA-buffer and lifetime corrections.
- `tests/run.py`: local-source checksums, imported-file blob checks, corrective
  patch application to the driver, and actual-function C regressions.
- `docs/BUILD-AND-VALIDATION.md`: build handoff, review scope and open gates.

## Verify without flashing

Requires Python 3, git and a C compiler with AddressSanitizer/UndefinedBehaviorSanitizer.
From a fresh clone, as a normal user:

```sh
python3 tests/run.py
```

This performs no network requests, mounts, device I/O or privileged operations.
It compiles selected functions extracted from the actual patched driver with
mocked kernel APIs. Passing does **not** prove a full kernel build, DMA operation,
firmware authenticity, postmarketOS boot, local Plasma Mobile or physical touch.

## Current status

The original commit reports compilation against `sm61x5-mainline/linux` 7.2.3.
The corrective patch requires a new clean target-kernel/package build; do not
reuse that earlier compilation claim for the changed source.

USB PHY enablement and the earlier clock corrections are **not present in the
published board patches**. Reconcile the complete target tree and its final DTB
before claiming USB works. Supply/power requirements remain board-specific checks.

Native display support for the `lide_hsd` HX83102E panel is not implemented.
The board describes a bootloader-handoff simple framebuffer, whose geometry,
address and power behaviour still require hardware validation.

Touch firmware provisioning, full zero-flash error propagation, panel-only
power coordination, module-list verification, the final Plasma Mobile rootfs
and repeated physical acceptance tests remain open.

Rootfs stays on microSD. Device metadata selects Samsung Download Mode BOOT
flashing; this is not permission to write any device. No flash command is run
by this repository's tests or CI. See the validation guide before installation.
