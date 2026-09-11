# Boot dependency repair and stock-image control

This change follows the boot-path review on merged main `42fd2e45bde2e1b867cfbe458547c824c7a137a5`.
It repairs concrete native-board dependencies; it does not claim that the
frozen-logo failure has been reproduced or fixed on hardware.

## Implemented

- Patch `0005` enables the GENI wrapper that creates the existing SPI/UART
  children and the GPI DMA provider already selected by SPI0.
- The SD host now references board-local default/sleep pin states. Data-drive and
  GPIO88 card-detect pin settings are translated from the pinned donor's
  `sdc2_*` / `cd_*` definitions. Card-detect polarity is unchanged.
- APKBUILD includes that patch and increments the kernel package release.
- Host tests and target CI consume the actual APKBUILD patch list with its
  checksums, rather than assuming there are exactly four patches.
- Added-source checks cover the enabled GENI/DMA nodes and connected SD
  pin states. Target CI compiles the entire device-tree patch series.
  These checks do not certify all referenced providers or runtime drivers.
- CI runs on main and PRs. It validates the real target DTB and attempts a
  full target `vmlinux` link; an object-only build is not a link result.
- A static ARM64 diagnostic `/init` and deterministic cpio builder separate
  kernel/userspace entry from SD, systemd, graphics and touch bring-up.

## Evidence versus stock

No authenticated Samsung stock BOOT/DTBO pair was available in the review
runtime. The supplied historical `boot.img` is a postmarketOS image:

```
62e18166aed5c1f29209a5bb828dbc55235675d5b07dd4ef001439b7a3c4c483
```

It contains `pmos_boot_uuid` and `pmos_root_uuid` arguments. It is not a
Samsung control. A path named `recovery/boot.img`, partition-sized padding,
or a filename saying stock does not independently establish provenance.
Historical notes also describe downloading LineageOS images into that
recovery directory; do not relabel those as Samsung firmware.

Use the actual pre-modification dump or a BOOT/DTBO pair extracted from the
matching Samsung firmware package. Record its firmware version, source,
original container hash and extracted image hashes. A current BOOT dump
may just be the already-flashed experimental candidate. Retain genuine
stock bytes locally; do not commit firmware or private device logs here.

## Stock comparison still required

No stock-versus-candidate binary comparison was completed here. The new
comparison helper was not published because its GitHub upload was blocked
by an indeterminate safety check. Do not claim this PR includes that helper.

Use the existing `tools/donor_bridge.py inspect` with ordinary local files
for BOOT/DTBO inventory. Record the exact stock source, its expected hash,
the failed candidate hash, all separate and appended DTB identities, and
the installed DTBO table. Do not infer the selected entry from its position.

A desktop-side offline test must explicitly identify the working stock base
DTB and the installed overlay entry using device evidence, then apply that
overlay to the stock and candidate bases with the standard `fdtoverlay`
tool. Record both exit statuses and errors, not only symbol-name overlap.
This does not require device writes. Success would test overlay application,
not Samsung selection, signature/AVB acceptance, driver bindings or boot.

The native candidate has a different device-tree structure from the vendor
base. Adding symbol generation alone or copying vendor overlays is not a
verified fix. This PR deliberately makes no DTBO or numeric-selector change.

## Diagnostic initramfs

```sh
mkdir -p evidence
python3 tools/build_diag_initramfs.py --output evidence/diagnostic
```

The output directory must not exist. The builder uses Clang/LLD and requires
no target libc, sudo or Alpine chroot. It verifies that `init` is an ELF64
AArch64 static executable with no interpreter/dynamic segment, then emits
`diagnostic-initramfs.cpio.gz` and a source/tool/output hash manifest.

This is ONLY a replacement ramdisk input for a separately prepared,
explicitly approved diagnostic Android BOOT candidate. It is not a kernel,
BOOT image, postmarketOS rootfs, SD filesystem image or installer. Preserve
all original candidate and restoration assets. Do not pass this cpio to a
partition writer. Keep kernel/DTB/DTBO choices fixed for a ramdisk-only
experiment and preserve the complete packing invocation and hashes.

As PID1 it emits `GTA4LWIFI_DIAG_INIT_ENTERED` to the console and kernel log,
mounts only devtmpfs/proc/sysfs, and emits a heartbeat. It never mounts SD or
internal filesystems, configures networking, exposes a shell, writes a block
device, toggles GPIOs, resets or flashes the tablet. Outside PID1 it performs
only a write/exit self-test, which CI exercises under qemu-aarch64. That
self-test does NOT prove kernel boot, PID1 mounts, console or ramoops work.

Silence from an unvalidated console is inconclusive. Compare the actual
ramoops writer/reader geometry, including ECC and retention, before using
pstore silence as evidence. Keep the diagnostic attempt attended; this
minimal environment has no normal power-management userspace.

## Deliberately unchanged / remaining gates

- No speculative board-selector, clock-frequency, reserved-memory, regulator
  voltage or DTBO changes. The earlier candidate selectors remain unverified.
- SD L7 bias behavior needs a target-driver-supported implementation and
  device evidence; an ignored vendor property is not a fix.
- Panel tables are not an enabled panel driver. Display handoff, local KWin
  and physical touch remain hardware tests, not CI successes.
- The previous Himax lifecycle/transport review remains open; enabling the
  controller does not fix those independent driver defects.
- Full APK packaging, matching rootfs/firmware and exact installed BOOT/DTBO
  comparison remain required. A successful `vmlinux` link is not an APK,
  runnable installation or resolution of the observed frozen logo.
- No write permission is expanded: BOOT plus the selected microSD only after
  the existing approval process. No automatic DTBO/VBMETA/recovery writes,
  bootloader unlock/relock, userdata erase or home-network changes.

## Primary references

- [Pinned donor kernel](https://github.com/jojobear691/kernel-samsung-sm6115-halium12/tree/c058c8a0930d4352eaa96a172f83515077e9ea62):
  `arch/arm64/boot/dts/vendor/qcom/bengal.dtsi` (`sdc2_*`, `cd_*`), and
  `P85946-qrd-overlay.dts` fragment 48. Donor source, not a stock-image dump.
- [GENI parent population](https://github.com/torvalds/linux/blob/08df884136f1c1197bab2a27814404fd329d9aac/drivers/soc/qcom/qcom-geni-se.c).
- [Overlay resolution](https://docs.kernel.org/devicetree/overlay-notes.html).
- [Android BOOT headers](https://source.android.com/docs/core/architecture/bootloader/boot-image-header).
- [Ramoops layout](https://docs.kernel.org/admin-guide/ramoops.html).

## Target-build correction

The first target run rejected `sdc2_on_state` / `sdc2_off_state`: those
labels are absent from the pinned kernel even though similarly named
compiled nodes exist. The repair now defines unique board-local states
under `tlmm`, with the donor's clock/command/data pad settings, instead
of assuming labels from another revision. Source regressions require all
four referenced board-state labels to be defined. The full-source target
DTB job remains the authoritative check that the complete tree compiles.
