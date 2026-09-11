# Ubuntu Touch control first; preserve the hardware stack

Final acceptance stays unchanged: **postmarketOS boots, local Plasma Mobile
runs, physical touch works**. Native/mainline kernel development is a means,
not a fourth requirement. Ubuntu Touch/Lomiri is a control, not the deliverable.

## Source authority and release boundary

Use the supplied `INSTALLATION_GUIDE_USE_THIS_GUIDE` as the installation
reference, not the older `Install_Directions.txt` inside the archive. The two
uploaded guide copies are byte-identical. The guide documents June 5, 2026;
`RECENT-UPDATES-20260620.txt` describes a separate June 20 refresh. Do not combine
their images, helpers or claimed test results. A newer filename is not a
replacement for the evidenced baseline.

| Input required by the guide | SHA-256 |
| --- | --- |
| `SM-T500-gta4lwifi-UbuntuTouch-24.04-Halium12-FULL-INSTALL-PACK-WORKING-AUDIO-WIFI-20260605.tar.gz` | `82f3cb5bcd7da1d73f8df96d43ac74e2d7dbb18e87bb8435319141946211d0fa` |
| `lineage-19.1-20260529-UNOFFICIAL-gta4lwifi-nofirmwareassert.zip` | `f3f88ac09843afd7fc07e6e6ff5202af4b4ba016f1a52805230156c7745ed85a` |
| `OrangeFox-R11.3-Unofficial-gta4l.zip` | `b84fec44e54577d2ffe85fb2b2ef2c54fe7a83c0a07b269d03c235b79f119697` |

These are guide-provided identities, not files newly downloaded or validated
in this change. Verify outer and inner checksums as the guide directs. The
June 20 snapshot is not the control in this table.

## What we must reproduce, not silently skip

| Working route in the guide | Why copying just BOOT is not equivalent |
| --- | --- |
| Exact Android 12 / LineageOS 19.1 installation | The guide says its updater writes system/vendor/product/ODM plus BOOT, DTBO and vbmeta with flags 3. A different base is not covered. |
| Userdata reformatted as ext4 | The Halium boot script expects that filesystem. Our SD filesystem is not automatically a substitute. |
| Matched June 5 BOOT and DTBO | They are a pair; a native DTB with a vendor overlay is a different experiment. |
| `/data/rootfs.img` and `/data/system.img` | The Halium ramdisk locates these images and mounts the Android image for LXC. Our pmos UUID lookup does not implement that contract. |
| First Lomiri boot | This is the known-working control checkpoint, not proof of Plasma compatibility. |
| Bundled audio/Wi-Fi layer after boot | This follows first boot; adding these services cannot repair failure to enter the kernel. |

The guide's full procedure erases userdata and writes boot-critical partitions
outside the previous BOOT-plus-microSD scope. **This document does not authorize
or automate that transition.** Do not execute it merely because it is linked
here. Preserve verified restoration assets and obtain explicit approval before
those destructive steps. No device writes were performed for this change.

## New finding: test the donor's existing DRM before rewriting display

At kernel source commit `c058c8a0930d4352eaa96a172f83515077e9ea62`:

- `arch/arm64/configs/gta4l_eur_open_defconfig` selects `CONFIG_ARCH_BENGAL=y`.
- `techpack/display/Makefile` includes `config/bengaldisp.conf` for BENGAL.
- That config enables `CONFIG_DRM_MSM`, `CONFIG_DRM_MSM_SDE` and
  `CONFIG_DRM_MSM_DSI`.
- `techpack/display/msm/msm_drv.c` advertises MODESET, ATOMIC, GEM, PRIME and
  RENDER, registers `dumb_create`/`dumb_map_offset`, and names its DRM driver
  **`msm_drm`**.

This is a specific reason to test the existing display stack, not evidence
that its ABI already works with KWin/Mesa. The source revision is not proven
to reproduce the June 5 released kernel. Inspect the actual running control.
Do not infer usable hardware acceleration from `DRIVER_RENDER` or a render
node. Vendor KGSL, display buffers, fences and userspace APIs need real tests.

KDE's 2020 decision to drop the old Halium integration does not prohibit using
a downstream kernel through standard Linux interfaces. Conversely, a working
Lomiri/Halium display does not certify current Plasma Mobile. Neither blanket
assumption is a substitute for testing KMS, buffer allocation and input.

## Smallest useful experiment sequence

1. **Exact control:** reproduce the guide's matched release only under the
   separately approved write scope. Record the actual kernel, image hashes,
   baseline, display and physical touch results. Do not change to June 20 mid-test.
2. **Kernel-entry isolation:** keep the donor kernel and compatible DTB/DTBO
   fixed. Use the static diagnostic ramdisk from [PR #3](https://github.com/ryan-winkler/gta4lwifi-postmarketos/pull/3)
   only as a separately packed candidate; it is not in main until that PR lands.
   Preserve the donor header values and record the repacking command.
   This tests kernel/userspace entry, not postmarketOS or Plasma. No new packer.
3. **postmarketOS userspace:** retain the proven hardware pair and boot a
   minimal postmarketOS userspace. Check the chosen init's kernel requirements
   against the donor's Linux 4.19 first. Adapt the root-image/mount contract
   deliberately; renaming our SD partition image `rootfs.img` proves nothing.
4. **Standard graphics/input:** inventory real DRM connectors/planes and input
   devices, then test a local frame and input under a controlled compositor
   session. Test a supported software-rendering path before GPU optimization.
   Do not run competing display masters or count recovery's display as the OS.
5. **Full Plasma:** verify the actual installed package contents, KWin, shell,
   session startup, physical tapping/dragging and repeat boots. Return to native
   driver work only for a demonstrated incompatibility that blocks this route.

Each experiment changes one layer. A successful compile or a QEMU non-PID1
self-test is not a successful tablet boot. The current native branch remains
available; it is no longer assumed to be the shortest first-boot path.

## Read-only runtime evidence

The small collector uses existing shell tools; it does not install, mount,
repack, flash, read raw partition contents, change services or record keystrokes.
Its context label is caller-supplied, not authentication of the running image.
Its `modetest -M msm_drm -c -p` invocation is query-only and bounded by timeout.
Permission failures or unavailable tools are reported, not interpreted as a
missing driver or a successful test. It excludes raw cmdline, serial properties,
network state and private configuration; review output before sharing anyway.

From the desktop, against the explicitly selected recovery device:

```sh
mkdir -p evidence
adb -s "$TABLET_SERIAL" shell sh -s -- recovery \
  < tools/collect-ut-control.sh > evidence/recovery-observations.txt
```

For a running Ubuntu Touch control, run the same file through its already
verified SSH connection with argument `ubuntu-touch`. Use `postmarketos` only
for the actual postmarketOS runtime. Recovery observations describe recovery,
not the installed BOOT. No actual device capture was performed here.

## References

- [Donor port](https://github.com/jojobear691/ubuntu-touch-samsung-gta4lwifi)
  (`deviceinfo`, `build.sh`): published build configuration, not June 5 binary proof.
- [Pinned donor display config](https://github.com/jojobear691/kernel-samsung-sm6115-halium12/blob/c058c8a0930d4352eaa96a172f83515077e9ea62/techpack/display/config/bengaldisp.conf).
- [Pinned donor DRM registration](https://github.com/jojobear691/kernel-samsung-sm6115-halium12/blob/c058c8a0930d4352eaa96a172f83515077e9ea62/techpack/display/msm/msm_drv.c#L1842-L1884).
- [UBports architecture and one-change-at-a-time guidance](https://docs.ubports.com/en/latest/porting/introduction/Intro.html).
- [KDE's historical Halium decision](https://plasma-mobile.org/2020/12/14/plasma-mobile-technical-debt/).
