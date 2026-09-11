# Donor integration: postmarketOS, Plasma Mobile and physical touch

## What changed

This branch starts from `7181ab545180a313723995b90aeaab7c9af335c6`.
It keeps the existing near-mainline kernel, SPI Himax port, native postmarketOS
userspace, and microSD rootfs design. It does not replace them with Ubuntu Touch,
Lomiri, an Android rootfs, or proprietary Android graphics libraries.

Two additional patches are included in the kernel APKBUILD, with package revision
3 and calculated source checksums:

- `0003-reconcile-donor-boot-and-supplies.patch`: source-backed SoC and board
  selection candidates, fixed clocks, USB supplies, SD supply mapping, and an
  explicit touchscreen firmware filename.
- `0004-select-himax-firmware-from-device-property.patch`: the existing SPI
  driver reads `firmware-name` before allocation. Invalid explicit properties
  return an error, rather than silently choosing a fallback. The existing
  Android-command-line fallback is preserved for other boards.

**These are bring-up changes, not a verified boot fix.** No new BOOT, DTBO,
rootfs, or firmware binary is distributed by this branch.

## Pinned hardware reference

Repository: `jojobear691/kernel-samsung-sm6115-halium12`
Commit: `c058c8a0930d4352eaa96a172f83515077e9ea62`

| File | Git blob identity |
|---|---|
| `arch/arm64/boot/dts/vendor/qcom/bengal.dtsi` | `a397c0d6848c873b95de36f81fe11122bd1c148f` |
| `arch/arm64/boot/dts/vendor/qcom/P85946-qrd-overlay.dts` | `9f8e83cb2745b0c3f050d132c17f66ebaee92bef` |

These are public Samsung/Qualcomm-derived source declarations used by the Ubuntu
Touch port. They are not live measurements from Ryan's tablet, and their source
identity does not establish correspondence to a particular working release image.
The donor's own provenance document explicitly leaves some prebuilt-image/source
correspondence unresolved.

The adaptation reference is
`jojobear691/ubuntu-touch-samsung-gta4lwifi` at
`890cdcfa4a8edbe1acd26194fee9ce8a3bf988aa`. LineageOS provides a second structural
reference through `android_kernel_samsung_sm6115` and
`android_device_samsung_gta4l-common`. The active changes below are traceable to
the pinned donor files rather than moving LineageOS branch heads.

## Translation decisions and limits

| Item | Existing code | Source-backed candidate | Evidence boundary |
|---|---|---|---|
| SoC IDs | 445, 420 | 417, 444; revision `0x10000` | Matches donor base; verify the bootloader-selected FDT. |
| Board selector | `0x85943,1` | `0x1000b,0` | This is the donor **overlay** selector. Our flattened board arrangement differs; not proven valid on hardware. |
| XO fixed clock | Absent | 19,200,000 Hz | Donor declaration. |
| Sleep fixed clock | Absent | **32,764 Hz** | Donor declares `0x7ffc`; earlier experiment used 32,768. Do not hide this discrepancy. |
| QUSB2 digital / PLL / DPDM | Absent | PM6125 L4 / L12 / L15 | Resolve phandles to regulator names, then translate binding names. |
| QMP PHY / PLL | Absent | PM6125 L4 / L12 | Native binding uses `vdda-phy-supply` / `vdda-pll-supply`. |
| SD card / I/O | Absent | PM6125 L22 / L5 | Resolve external overlay fixups through base symbols. |
| Touch firmware selection | Android panel substring | `Himax_firmware_lide_hsd.bin` property | Selection only; firmware availability and controller readiness remain separate. |

**No new voltage limits are copied.** The donor's L15 maximum voltage is actually
a three-byte string, not a valid u32. The generated facts preserve those raw bytes
and flag the malformed property; they do not infer a voltage from it. Existing
native regulator constraints are unchanged. The vendor SD I/O-bias supply L7 is
recorded but not silently mapped to an unrelated mainline property. Full SD pin,
bias, and power sequencing still need review in the real target kernel.

The numeric Qualcomm board selector is not derived from the Android string
`P85943DA1`. A live selected tree or a demonstrably working image pair must resolve
the source/layout discrepancy before this candidate is approved for a test flash.
Changing a selector could change which currently installed vendor DTBO is applied.
Do not install the donor DTBO beside this kernel as a shortcut.

## Exact panel work delivered

`tools/regenerate_donor.py` verifies both complete source files, compiles them with
`dtc`, and regenerates:

- `reference/donor-hardware.json`: machine-readable board/supply/clock/panel
  declarations, source identities, anomalies and verification limits.
- `experimental/panel/hx83102e_lide_commands.h`: portable C command data for the
  exact `/fragment@23/__overlay__/qcom,mdss_dsi_hx83102e_lide_hsd_video` node.

Generated outputs are kept in CI artifacts and the worked-files bundle, rather
than duplicating the large source-derived data in Git.

The generated header contains **seven command sequences and 67 records**:
47 on, four off, two diming-off (donor spelling), six deep-standby, four master,
two client, and two status-read records. Type, last-command marker, channel, ACK,
delay, payload length, and payload bytes are preserved. A compiled C test
re-serializes every table and compares the resulting bytes with the donor.

**These tables are not a complete panel driver and are not linked into the kernel.**
That is deliberate: the donor has special hxlide/hx83102e display behaviour,
last-command batching, DSI host assumptions, panel-power ordering and brightness
handling that a generic command-array copy does not implement. The next panel
change must review `techpack/display/msm/dsi/dsi_panel.c` and the target DRM APIs.
Do not remove metadata, replay all sequences at probe, or label generated data
as working display support.

The donor panel uses reset GPIO 81 and VCC GPIO 71. The existing **touchscreen**
reset GPIO remains 31 and IRQ GPIO remains 80; these signals are not interchangeable.
The panel mode is 1200x2000, 60 Hz, four lanes, video/non-burst-sync-event, with
24/24/24 horizontal porches/pulse and 228/10/4 vertical front/back/pulse. The
source orientation is 180 degrees. These are reference values, not a licence to
program unverified GPIOs or bypass panel supply validation.

## Reproduce the checks on the Linux desktop

Use a clean worktree, not the synced Vault. Required host tools: Python 3, Git,
GCC, GNU Make and device-tree-compiler (`dtc`). No privileged operation occurs in
these commands. Package installation, when needed, is a separate host decision.

```sh
python3 tools/fetch_donors.py
python3 tools/regenerate_donor.py --write
bash tools/verify-donor-integration.sh
```

The fetcher downloads only the two pinned public source files, verifies their Git
blob identities, refuses a symlinked cache and does not overwrite changed cache
files. The verifier compiles reference data, compares generated outputs, checks
local package checksums and shell syntax, applies the relevant patch subset,
and runs parsing plus C regressions. It does not execute donor code or flash.

Regenerate intentionally after reviewing a source/generator change:

```sh
python3 tools/regenerate_donor.py --write
python3 tools/regenerate_donor.py
```

Inspect the actual failed Android boot image, a donor boot image and the actual
installed DTBO backup as separate regular files:

```sh
python3 tools/donor_bridge.py inspect /path/to/failed-android-boot.img > failed-boot.json
python3 tools/donor_bridge.py inspect /path/to/known-working-boot.img > reference-boot.json
python3 tools/donor_bridge.py inspect /path/to/installed-dtbo-backup.img > installed-dtbo.json
```

The inspector follows Android component boundaries, DTBO table entries and FDT
sizes. It does not blindly search for magic. It supports FDT v17, Android boot
v0-v2, and uncompressed DTBO table v0. Unsupported compressed DTBO versions fail;
non-gzip appended-kernel DTBs are explicitly not inspected. It does not authenticate
AVB, validate electrical wiring, determine the bootloader's selection, or certify
bootability. It refuses direct block-device inputs; use verified read-only backups.

For independent target DTB compilation, supply the exact kernel archive named
and SHA-512-pinned in APKBUILD:

```sh
bash tools/check-target-dtb.sh /path/to/linux-sm6115-7.2.3.tar.gz
```

This uses a fresh temporary tree, applies **all four patches**, runs target
configuration generation and builds the board DTB. It requires the target build
tools (Clang/LLVM, Make, Flex, Bison and the host development headers). It is not a
full kernel/module link or an Alpine package build. Source/host tests passing is
not a substitute for that full build.

## Integration sequence after these files

1. Reconcile the actual failed image with the published commit and local changes.
   Compare both appended and separate DTBs, selected live FDT, installed DTBO,
   BOOT addresses and root filesystem identifiers. UT and Lineage source disagree
   about the ramdisk address; retain the existing address until working-binary
   evidence resolves it. Do not rewrite verified SD filesystems merely because
   the packing tool or kernel changed.
2. Build the patched kernel and its matching modules through the real package
   workflow. Verify the final resolved configuration and exported components.
   Provision the correct touch firmware at the time it is requested; this PR
   contains no firmware binary and does not fix the entire zero-flash error chain.
3. Use a recoverable, explicitly approved BOOT-only diagnostic candidate to
   establish kernel/initramfs/SD-rootfs progress. Capture logs, not just the logo.
   A known-working downstream control must retain its compatible DT/ramdisk
   environment; it is not an interchangeable Linux 7.2 image component.
4. Validate framebuffer redraw/DRM output and physical input. Complete the native
   panel implementation where the handoff is insufficient. Do not start porting
   an Android hardware-composer stack into KWin without a separate design and
   demonstrable supported graphics interface.
5. Complete the native Plasma Mobile/systemd session, including keyboard,
   app switching, lock/unlock, three cold boots and display off/on physical touch.

The existing PR #1 overlaps main's direct touch changes. This branch is built
on updated main and does not reapply PR #1's old corrective patch blindly.

## Non-negotiable safety and status

No formatting, sudo, ADB, flashing or repartitioning is performed by the source
helpers. BOOT and microSD remain the installation boundary. VBMETA, DTBO,
RECOVERY, USERDATA, bootloader unlock/relock and a full UT installation are not
implicitly authorised. Do not copy donor Android init scripts or broad permissions
into postmarketOS. Keep diagnostic USB isolated; final unauthenticated failure
shells must be reviewed separately.

Status must remain **NOT TESTED on hardware** until evidence ties a candidate's
hashes to postmarketOS boot, local Plasma Mobile and real touch. A source-backed
patch, generated panel table, passing host test, or selected firmware filename
is not proof of any of those outcomes.

## Primary references

- https://github.com/jojobear691/kernel-samsung-sm6115-halium12/tree/c058c8a0930d4352eaa96a172f83515077e9ea62
- https://github.com/jojobear691/ubuntu-touch-samsung-gta4lwifi/blob/890cdcfa4a8edbe1acd26194fee9ce8a3bf988aa/docs/PROVENANCE.md
- https://github.com/jojobear691/ubuntu-touch-samsung-gta4lwifi/blob/890cdcfa4a8edbe1acd26194fee9ce8a3bf988aa/docs/INSTALL.md
- https://github.com/LineageOS/android_device_samsung_gta4l-common/blob/lineage-23.2/BoardConfigCommon.mk
- https://source.android.com/docs/core/architecture/dto/partitions
- https://source.android.com/docs/core/architecture/dto/multiple
- https://github.com/torvalds/linux/blob/08df884136f1c1197bab2a27814404fd329d9aac/Documentation/devicetree/bindings/phy/qcom,qusb2-phy.yaml
- https://github.com/torvalds/linux/blob/08df884136f1c1197bab2a27814404fd329d9aac/Documentation/devicetree/bindings/phy/qcom,msm8998-qmp-usb3-phy.yaml
- https://github.com/KDE/kwin/commit/7e5c16989e706af65ffc4635688e9499824077a3
