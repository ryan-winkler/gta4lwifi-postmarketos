#!/bin/sh
# Read-only observations from Android/recovery or a booted Linux control.
# No mounts, partition reads/writes, service changes or input-event recording.
set -u
LC_ALL=C
export LC_ALL
case "${1:-}" in
    recovery|ubuntu-touch|postmarketos|diagnostic) context=$1 ;;
    *) echo 'Usage: sh collect-ut-control.sh {recovery|ubuntu-touch|postmarketos|diagnostic}' >&2; exit 64 ;;
esac
case "$(uname -m)" in
    aarch64|armv8l) ;;
    *) echo 'Not an ARM64 tablet runtime; run this through its ADB/SSH shell.' >&2; exit 2 ;;
esac
report() {
    printf '\n--- %s ---\n' "$1"
    shift
    "$@" 2>&1 || printf 'UNAVAILABLE (exit %s)\n' "$?"
}
printf 'OBSERVATIONS ONLY; context label is caller-supplied: %s\n' "$context"
echo 'Recovery observations describe the recovery kernel, not the installed BOOT.'
report 'Running kernel (no hostname)' uname -srm
if command -v getprop >/dev/null 2>&1; then
    for prop in ro.product.model ro.product.device ro.build.version.release ro.build.version.sdk ro.build.id ro.vendor.build.fingerprint ro.odm.build.fingerprint ro.boot.flash.locked ro.boot.verifiedbootstate; do
        report "$prop" getprop "$prop"
    done
else
    echo 'Android properties unavailable: model/vendor/AVB baseline NOT VERIFIED.'
fi
for f in /sys/firmware/devicetree/base/model /sys/firmware/devicetree/base/compatible; do
    [ -r "$f" ] && report "$f" tr '\000' '\n' < "$f"
done
report 'Root/data mount types (no mount options)' awk '$2=="/" || $2=="/data" || $2=="/userdata" {print $1,$2,$3}' /proc/mounts
for image in /data/rootfs.img /data/system.img /userdata/rootfs.img /userdata/system.img; do
    [ -f "$image" ] && report "$image size" stat -c '%n %s bytes' "$image"
done
for part in boot dtbo vbmeta userdata; do
    [ -e "/dev/block/by-name/$part" ] && report "$part path only" readlink -f "/dev/block/by-name/$part"
done
report 'DRM device nodes' ls -l /dev/dri
for f in /sys/class/drm/card*-*/status /sys/class/drm/card*-*/modes /sys/class/input/event*/device/name /sys/class/input/event*/device/capabilities/abs; do
    [ -r "$f" ] && report "$f" cat "$f"
done
if command -v modetest >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
    # Query only. Do not add -s/-P/-w or stop a running compositor here.
    report 'Donor msm_drm connectors/planes (query only)' timeout 10 modetest -M msm_drm -c -p
else
    echo 'modetest/timeout unavailable: DRM API query NOT TESTED.'
fi
echo 'Collection finished. This is NOT a hardware acceptance or flash-approval result.'
