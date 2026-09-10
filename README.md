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
    current kernel's GPIO descriptor, SPI, PM, and proc_ops APIs.

## Status

- Device tree, defconfig, and touch driver compile cleanly against
  `sm61x5-mainline/linux` 7.2.3.
- USB PHY nodes (`usb_hsphy`, `usb_qmpphy`) enabled; disabled by default
  upstream, no board-specific supply properties required.
- Native DRM/display (panel driver for the `lide_hsd` HX83102E panel
  variant) not yet ported; boot relies on a bootloader-handoff
  simple-framebuffer node in the device tree.
- Rootfs, boot image, and physical hardware validation not yet complete.
