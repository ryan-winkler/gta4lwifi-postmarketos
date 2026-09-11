# gta4lwifi postmarketOS port

Device and kernel package files for postmarketOS on the Samsung Galaxy Tab A7
10.4 (2020) Wi-Fi, SM-T500 (`samsung-gta4lwifi`).

## Layout

- `device/testing/device-samsung-gta4lwifi/` — device package (deviceinfo,
  module list, APKBUILD).
- `device/testing/linux-postmarketos-qcom-sm6115/` — kernel package, built
  from `sm61x5-mainline/linux` (near-mainline SM6115 tree):
  - `0001-add-samsung-gta4lwifi-support.patch` — board device tree,
    defconfig, battery driver ID.
  - `0002-fix-touch-node-and-port-himax-hx83102-spi-driver.patch` — corrects
    the touch device-tree node to the driver's actual DT properties and
    ports the SPI Himax HX83102 touchscreen driver from Samsung's GPL
    kernel source (drivers/input/touchscreen/hxchipset), adapted for the
    current kernel's GPIO descriptor, SPI, PM, proc_ops and logging APIs,
    with initial PM, GPIO and transport adaptations. The post-merge review
    still identifies lifecycle, error-propagation and DMA-safety defects;
    successful compilation is not touchscreen acceptance.

## Provenance

- Kernel source: `https://codeberg.org/sm61x5-mainline/linux`, tag
  `sm61x5/7.2.3`, tarball sha512 in the kernel package's `APKBUILD`.
- Touch driver donor: Samsung's published GPL kernel source for SM-T500/T505
  (`drivers/input/touchscreen/hxchipset`), matched to this exact unit via
  `androidboot.board_id` and the live DSI panel compatible string.
- pmaports base: postmarketOS `main` branch (device/kernel packages here
  overlay onto a full pmaports checkout; this repo alone is not one).

## Status

- The pre-integration baseline was reported to build and link
  end-to-end against `sm61x5-mainline/linux` 7.2.3 (`make ARCH=arm64`, full
  `vmlinuz`/modules, not just the touch driver in isolation). The new integration
  patches require a fresh target-kernel/package build; that prior result does not
  verify the modified candidate.
- USB PHY nodes (`usb_hsphy`, `usb_qmpphy`) and `CONFIG_REGULATOR_QCOM_RPM`
  (needed by the board's own `qcom,rpm-pm6125-regulators` node) enabled;
  neither was on by default upstream.
- `deviceinfo`/`modules-initfs` corrected to the verified Samsung Download
  Mode flash method (`heimdall-bootimg`, not fastboot) and the actual
  loadable module set from a real build (most of the earlier list — pinctrl,
  the PMIC MFD driver, the battery gauge, the early console — turned out to
  be built-in, not modules; `freedreno` was never a kernel module at all).
- Native DRM/display (panel driver for the `lide_hsd` HX83102E panel
  variant) not yet ported; boot relies on a bootloader-handoff
  simple-framebuffer node (`CONFIG_DRM_SIMPLEDRM`) in the device tree.
- Not yet done: a full pmaports-integrated build (pmbootstrap/abuild) of
  this exact source, rootfs, boot image, and physical hardware validation.


## Donor-backed integration candidate

The current integration adds two separate kernel patches (`0003` and `0004`):
boot-selector/clock/USB/SD supply reconciliation and explicit Himax firmware
selection. It preserves the existing postmarketOS + Plasma Mobile + microSD
architecture; it does not install Ubuntu Touch or replace KWin with Lomiri.

[Read the integration record](docs/DONOR-INTEGRATION.md) before building. The
record distinguishes donor declarations, translated bindings, unresolved board
selection, and actual hardware evidence. Native display remains unfinished.

```sh
python3 tools/fetch_donors.py
python3 tools/regenerate_donor.py --write
bash tools/verify-donor-integration.sh
```

The exact Lide panel's seven command sequences are available as generated C data
under `experimental/panel/`, with reproducible source facts under `reference/`.
They are **not an enabled panel driver**. No OS image is supplied by these checks.

## Boot dependency follow-up

See [BOOT-PATH-FIX.md](docs/BOOT-PATH-FIX.md) for the GENI/SD repair,
stock/candidate evidence requirements and static diagnostic initramfs. These are source/diagnostic improvements, not hardware sign-off.
