# Build and validation handoff

## Scope of this correction

Base reviewed: `7f2b9f9417212c01b70f261892a4cafde8b55323`.
Keep the Samsung donor and original board/touch patches; apply `0003` afterward.
The kernel APKBUILD lists it and bumps pkgrel. Device metadata also bumps pkgrel
and selects `heimdall-bootimg` / `BOOT`, without changing the recorded boot-header
version or load offsets.

`0003` addresses these concrete defects:

- Register the existing system PM table and forward callback failures. A failed
  firmware-restore callback keeps the suspended state; this is not panel-only PM.
- Stop freeing the outer state in common deinit. Probe/remove owns it. Cancel
  firmware/resume work before releasing report/input data, and use the input
  core's unregister operation only for successfully registered devices.
- Construct the firmware filename afresh with bounded formatting, including
  fallback, so repeated probes do not append or overflow.
- Preserve mandatory GPIO lookup errors, including deferred probe. Treat only
  ENOENT as absence of the optional 3v3 GPIO. Check direction and IRQ translation
  results, and propagate them through common initialization.
- Require the board's IRQ instead of starting an unowned polling worker after
  registration failure. Request it disabled, then enable it through the existing
  firmware initialization path. Queue firmware work only after common init.
- Bounce SPI command and response buffers through heap allocations, preserving
  one message and its command/response chip-select continuity. Check limits,
  allocation failures, short reads and copy-out only on successful completion.
  Bound writes to the existing staging buffer and controller limits.
- Replace the inherited I2C Kconfig dependency with SPI_MASTER; retain warnings
  and errors when the optional vendor debug subsystem is disabled.

## Reproducible build path

This repository supplies two ports, not a complete builder. On the real Linux
host, record the installed pmbootstrap version, full pmaports commit, compiler,
selected kernel commit/archive digest and the overlay commit. Do not invent
missing provenance or use the Asahi host kernel's headers as the tablet target.

Copy these two port directories into a dedicated, explicitly selected full
pmaports worktree only after comparing any existing copies. Preserve local
patches. Do not point pmbootstrap at this overlay as its entire aports tree.

Use the configured pmbootstrap instance to build the kernel and device packages,
then generate a **new matching** boot/rootfs pair with Plasma Mobile and the
supported systemd integration. Check the installed version's `--help` before
using wrapper/CLI options. Never suppress unresolved-symbol errors or replace
required hardware operations with success-returning stubs.

The APKBUILD's archive URL and SHA-512 remain the reviewed values. They were not
changed to an unverified upstream revision. Verify the archive digest and prepared
source, apply **all three** patches, generate the final configuration, compile
and fully link the target. Run additional warnings, Sparse, DT binding/schema
checks and package checks. Capture the complete logs and investigate regressions
rather than treating host unit tests as equivalent to these checks.

For the actual built-in driver configuration, verify the final `.config` contains
SPI and the Himax chipset/common/incell/HX83102 options. Reconcile `modules-initfs`
against the new kernel's real module/builtin metadata; its historic entries are
not newly validated by this PR.

## Firmware and remaining driver work

The donor reference is Samsung-origin code mirrored at:
`yoshimo/Samsung_Galaxy_Tab_A7_GTA4LX_SM-T500-SM-T505_Kernel`, commit
`3af0a970cb212758cd94a0d1df6079b805f2e7c1`.

The existing cmdline-based selector derives `Himax_firmware_lide_hsd.bin` for the
reported panel. No firmware binary is added or authenticated by this PR. Verify
it against the working tablet/matching firmware, record its hash and provenance,
and supply it when the driver requests it (initramfs when needed). A reproducible,
documented device-property selector is still preferable to Android cmdline parsing.

**Open before claiming a working installation:**

1. Audit the full zero-flash upload/checksum/readiness chain. The imported
   `i_update_FW()` calls a void updater then assigns success; this PR does not
   make that a verified controller-ready result. Implement returned errors,
   bounded parser/transfer checks and a controlled retry strategy. A missing
   firmware file must not produce a false-ready device or an IRQ storm.
2. Validate panel power sequencing and implement/verify display-only off/on
   separately from system suspend. Connecting `.pm` is not panel integration.
3. Review remaining vendor factory/proc and alternate-chip paths. This is a
   focused correction of the selected incell HX83102 path, not an audit of the
   complete vendor framework. Keep optional factory/debug interfaces off.
4. Resolve board clocks, PHY/supply dependencies, SD power/pinctrl and display
   from device-specific evidence; inspect the final DTB inside the exported boot
   image. Do not guess voltages, GPIOs, panel variants or reserved-memory ranges.
5. Validate the actual Plasma executables, mobile shell resources, session start,
   authentication/lock integration, runtime libraries and firmware in the rootfs.
   Package names need not equal executable names.

## Evidence and release boundaries

`python3 tests/run.py` checks six local source hashes, shell syntax, complete
imported driver-file Git blob identities, patch application to those files,
50 actual-function C cases under ASan/UBSan, and source contracts for PM/teardown.
It deliberately does **not** call pmbootstrap or flash utilities. Patching the
parent touchscreen Kconfig and the entire upstream tree still needs the real
package build. The remote source archive is verified there, not by these offline
local-source checks.

A controlled test flash needs physical SM-T500 identification, exact BOOT/SD
selection, image hashes/sizes, matching rootfs UUID, and verified restoration
assets, followed by the owner's explicit write approval. Do not alter VBMETA,
DTBO, RECOVERY, bootloader state or internal rootfs under that approval. Keep
bring-up USB networking isolated; check the final initramfs debug/failure shells
before daily-use sign-off.

Do not require completed hardware acceptance before the first controlled test
flash. Do require it before final release: three cold boots into the intended
postmarketOS microSD rootfs, local usable Plasma Mobile, physical multitouch and
keyboard interaction, contact release, lock/unlock, and continued touch after
screen off/on and reboot. Record PASS/FAIL/NOT TESTED with candidate hashes.

## Primary API references

- https://docs.kernel.org/driver-api/spi.html
- https://docs.kernel.org/driver-api/gpio/consumer.html
- https://docs.kernel.org/driver-api/input.html
- https://docs.kernel.org/kbuild/modules.html
