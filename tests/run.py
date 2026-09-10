#!/usr/bin/env python3
"""Non-flashing checks against the actual applied Himax source.

Requires Python 3, git and a C compiler with ASan/UBSan. No mounts, root,
network requests, or device access. These are host tests, not a kernel build.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'device/testing/linux-postmarketos-qcom-sm6115'
PREFIX = 'drivers/input/touchscreen/hxchipset/'


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def extract_added_files(patch, dest):
    """Extract complete new files from patch 0002, checking Git blob IDs."""
    count = 0
    for block in patch.split('diff --git ')[1:]:
        lines = block.splitlines(keepends=True)
        match = re.match(r'a/(\S+) b/(\S+)\n', lines[0])
        if not match or match[1] != match[2]:
            raise ValueError('unexpected patch path')
        path = match[2]
        if not path.startswith(PREFIX) or 'new file mode 100644\n' not in lines:
            continue
        rel = Path(path)
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('unsafe patch path')
        header = next(i for i, line in enumerate(lines) if line.startswith('@@ '))
        m = re.fullmatch(r'@@ -0,0 \+1,(\d+) @@\n', lines[header])
        if not m:
            raise ValueError('expected one complete new-file hunk')
        n = int(m[1])
        added = lines[header + 1:header + 1 + n]
        if len(added) != n or any(not line.startswith('+') for line in added):
            raise ValueError('incomplete new-file hunk')
        text = ''.join(line[1:] for line in added)
        tail = lines[header + 1 + n:]
        if tail and tail[0].startswith('\\ No newline at end of file'):
            text = text.removesuffix('\n')
        data = text.encode()
        expected = re.search(r'index 0+\.\.([0-9a-f]+)', block)[1]
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if not actual.startswith(expected):
            raise ValueError(f'new-file blob mismatch: {path}')
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        count += 1
    if count < 5:
        raise ValueError('missing driver source files')
    print(f'PASS: extracted and blob-verified {count} imported driver files')


def function(text, name):
    # Restricted extractor for the in-scope function bodies (no braces in
    # their comments/string literals). Fail on a missing or unclosed function.
    matches = list(re.finditer(r'^.*\b' + re.escape(name) + r'\([^;]*?\)\n\{', text, re.M))
    if not matches:
        raise ValueError(f'function missing: {name}')
    start = matches[-1].start()
    body = text.index('{', matches[-1].start())
    depth = 0
    for end in range(body, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return text[start:end + 1] + '\n'
    raise ValueError(f'unclosed function: {name}')


def check_sums():
    checked = 0
    for port in (ROOT / 'device/testing').iterdir():
        recipe = port / 'APKBUILD'
        if not recipe.exists():
            continue
        run(['sh', '-n', str(recipe)])
        for digest, name in re.findall(r'^([0-9a-f]{128})  (\S+)$', recipe.read_text(), re.M):
            if name.endswith('.tar.gz'):
                continue  # Remote tarball is verified by the real package build.
            path = port / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f'missing/unsafe local source: {path}')
            if hashlib.sha512(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f'checksum mismatch: {path}')
            checked += 1
    if checked != 6:
        raise ValueError(f'expected 6 local sources, checked {checked}')
    info = ROOT / 'device/testing/device-samsung-gta4lwifi/deviceinfo'
    run(['sh', '-n', str(info)])
    assert 'deviceinfo_flash_method="heimdall-bootimg"' in info.read_text()
    assert 'deviceinfo_flash_heimdall_partition_kernel="BOOT"' in info.read_text()
    print('PASS: six local checksums and three shell syntax checks')


PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
typedef uint8_t u8;
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define NO_PANEL 0
#define FW_SUFFIX ".bin"
#define GFP_KERNEL 0
#define HX_MAX_WRITE_SZ (64 * 1024 + 4)
#define HX_RST_PIN_FUNC 1
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define E(...) ((void)0)
#define I(...) ((void)0)
static size_t strscpy(char *dst, const char *src, size_t size) {
    size_t n = strlen(src);
    if (size) { size_t c = n < size - 1 ? n : size - 1;
        memcpy(dst, src, c); dst[c] = 0; }
    return n;
}
static unsigned panel;
static u8 himax_get_panel_info(void) { return panel; }
static struct { const char *panel_dsc; } himax_panel_info[] = {
    {"NULL"}, {"inx_fhd"}, {"txd_inx"}, {"hlt_auo"},
    {"txd_auo_al"}, {"txd_auo"}, {"lide_hsd"}
};
static char g_fw_name[64] = "Himax_firmware_";
struct gpio_desc { int id; };
struct spi_device { int unused; };
struct input_dev { int registered; };
struct himax_ts_data {
    struct spi_device *spi;
    struct input_dev *input_dev, *hx_pen_dev;
    bool input_registered, pen_registered;
    int hx_irq, use_irq, irq_enabled, irq_state;
};
static struct himax_ts_data state;
static struct himax_ts_data *private_ts = &state;
struct himax_i2c_platform_data {
    struct gpio_desc *gpio_reset, *gpio_irq, *gpio_3v3_en;
};
static int fail_at, step, injected, irq_result = 42;
static int next_error(void) { return ++step == fail_at ? injected : 0; }
static int gpiod_direction_output(struct gpio_desc *g, int value) {
    assert(g); (void)value; return next_error();
}
static int gpiod_direction_input(struct gpio_desc *g) {
    assert(g); return next_error();
}
static int gpiod_to_irq(struct gpio_desc *g) { assert(g); return irq_result; }
static void usleep_range(int a, int b) { (void)a; (void)b; }
static int irq_request_error;
static int himax_int_register_trigger(void) { return irq_request_error; }
#define atomic_set(p, v) (*(p) = (v))
static unsigned unregistered, freed;
static void input_unregister_device(struct input_dev *d) {
    assert(d->registered); unregistered++; free(d);
}
static void input_free_device(struct input_dev *d) {
    assert(!d->registered); freed++; free(d);
}
static size_t transfer_limit = 65536, message_limit = 65536;
static size_t spi_max_transfer_size(struct spi_device *d) { (void)d; return transfer_limit; }
static size_t spi_max_message_size(struct spi_device *d) { (void)d; return message_limit; }
static void *allocs[8]; static int alloc_count, alloc_fail_at;
static void *kmalloc(size_t size, int flag) {
    (void)flag;
    if (++alloc_count == alloc_fail_at) return NULL;
    void *p = malloc(size);
    for (int i=0;i<8;i++) if (!allocs[i]) { allocs[i]=p; return p; }
    abort();
}
static void *kmemdup(const void *src, size_t size, int flag) {
    void *p = kmalloc(size, flag); if (p) memcpy(p, src, size); return p;
}
static void kfree(void *p) {
    if (!p) return;
    for (int i=0;i<8;i++) if (allocs[i]==p) { allocs[i]=NULL; free(p); return; }
    abort();
}
static bool allocated(const void *p) {
    for (int i=0;i<8;i++) if (allocs[i] == p && p) return true;
    return false;
}
struct spi_transfer { const void *tx_buf; void *rx_buf; unsigned len; };
struct spi_message { struct spi_transfer *x[2]; int n; unsigned actual_length; };
static void spi_message_init(struct spi_message *m) { memset(m,0,sizeof(*m)); }
static void spi_message_add_tail(struct spi_transfer *x, struct spi_message *m) { m->x[m->n++]=x; }
static int sync_error, sync_calls; static bool short_read;
static int spi_sync(struct spi_device *s, struct spi_message *m) {
    (void)s; sync_calls++;
    assert(m->n==2 && allocated(m->x[0]->tx_buf) && allocated(m->x[1]->rx_buf));
    assert(((const u8 *)m->x[0]->tx_buf)[0]==0xf3);
    if (sync_error) return sync_error;
    memset(m->x[1]->rx_buf,0x5a,m->x[1]->len);
    m->actual_length=m->x[0]->len+m->x[1]->len-(short_read?1:0);
    return 0;
}
'''

TEST_MAIN = r'''
int main(void) {
    unsigned cases=0;
    for (panel=1;panel<7;panel++) {
        char expected[64]; snprintf(expected,sizeof(expected),"Himax_firmware_%s.bin",himax_panel_info[panel].panel_dsc);
        for(int i=0;i<20;i++) { assert(himax_assigned_fw_name()); assert(!strcmp(g_fw_name,expected)); }
        cases++;
    }
    panel=0; assert(!himax_assigned_fw_name()); assert(!strcmp(g_fw_name,"Himax_firmware.bin")); cases++;
    panel=255; assert(!himax_assigned_fw_name()); cases++;
    char large[200]; memset(large,'x',199); large[199]=0;
    panel=6; himax_panel_info[6].panel_dsc=large;
    assert(!himax_assigned_fw_name()); assert(!strcmp(g_fw_name,"Himax_firmware.bin")); cases++;

    struct gpio_desc g={0}; struct himax_i2c_platform_data p={&g,&g,&g};
    int errors[]={-EIO,-EINVAL,-517};
    for(unsigned e=0;e<ARRAY_SIZE(errors);e++) for(int i=1;i<=4;i++) {
        step=0; fail_at=i; injected=errors[e]; state.hx_irq=99;
        assert(himax_gpio_power_config(&p)==errors[e]); assert(state.hx_irq==0); cases++;
    }
    fail_at=0;
    for(unsigned e=0;e<ARRAY_SIZE(errors);e++) {
        irq_result=errors[e]; assert(himax_gpio_power_config(&p)==errors[e]); assert(state.hx_irq==0); cases++;
    }
    irq_result=0; assert(himax_gpio_power_config(&p)==-EINVAL); cases++;
    irq_result=42; assert(!himax_gpio_power_config(&p)); assert(state.hx_irq==42); cases++;
    p.gpio_3v3_en=NULL; assert(!himax_gpio_power_config(&p)); cases++;
    p.gpio_reset=NULL; assert(himax_gpio_power_config(&p)==-ENODEV); cases++;
    p.gpio_reset=&g;p.gpio_irq=NULL;assert(himax_gpio_power_config(&p)==-ENODEV);cases++;

    for(unsigned e=0;e<ARRAY_SIZE(errors);e++) {
        state.hx_irq=42;irq_request_error=errors[e];
        assert(himax_ts_register_interrupt()==errors[e]);assert(!state.use_irq);cases++;
    }
    irq_request_error=0;state.hx_irq=-517;assert(himax_ts_register_interrupt()==-EINVAL);cases++;
    state.hx_irq=42;assert(!himax_ts_register_interrupt());assert(state.use_irq&&!state.irq_enabled&&!state.irq_state);cases++;

    for(int mask=0;mask<4;mask++) {
        state.input_dev=calloc(1,sizeof(struct input_dev));state.hx_pen_dev=calloc(1,sizeof(struct input_dev));
        state.input_dev->registered=!!(mask&1); state.input_registered=!!(mask&1);
        state.hx_pen_dev->registered=!!(mask&2); state.pen_registered=!!(mask&2);
        unsigned oldunreg=unregistered, oldfree=freed;
        himax_release_input(&state);himax_release_input(&state);
        assert(!state.input_dev&&!state.hx_pen_dev);
        assert(unregistered-oldunreg==(unsigned)(!!(mask&1)+!!(mask&2)));
        assert(unregistered-oldunreg+freed-oldfree==2);cases++;
    }
    struct spi_device s={0};state.spi=&s;u8 command[]={0xf3,0x30,0},data[16];
    memset(data,0xa5,sizeof(data));
    assert(!himax_spi_read(command,3,data,16,3));assert(data[0]==0x5a);cases++;
    sync_error=-EIO;sync_calls=0;memset(data,0xa5,sizeof(data));
    assert(himax_spi_read(command,3,data,16,3)==-EIO);assert(sync_calls==3&&data[0]==0xa5);cases++;
    sync_error=0;short_read=true;assert(himax_spi_read(command,3,data,16,1)==-EIO);assert(data[0]==0xa5);cases++;
    short_read=false;
    for(int i=1;i<=2;i++) { alloc_count=0;alloc_fail_at=i;assert(himax_spi_read(command,3,data,16,1)==-ENOMEM);cases++; }
    alloc_fail_at=0;
    assert(himax_spi_read(command,3,data,16,0)==-EINVAL);cases++;
    assert(himax_spi_read(NULL,3,data,16,1)==-EINVAL);cases++;
    assert(himax_spi_read(command,3,NULL,16,1)==-EINVAL);cases++;
    transfer_limit=2;assert(himax_spi_read(command,3,data,16,1)==-EMSGSIZE);cases++;
    transfer_limit=65536;message_limit=2;assert(himax_spi_read(command,3,data,16,1)==-EMSGSIZE);cases++;
    message_limit=18;assert(himax_spi_read(command,3,data,16,1)==-EMSGSIZE);cases++;
    message_limit=19;assert(!himax_spi_read(command,3,data,16,1));cases++;
    for(int i=0;i<8;i++)assert(!allocs[i]);
    printf("PASS: %u actual-function C regression cases (ASan/UBSan)\n",cases);
}
'''


def driver_checks(folder, tmp, functions_only=False):
    platform = (folder / 'himax_platform.c').read_text()
    common = (folder / 'himax_common.c').read_text()
    c = PREAMBLE
    for name in ('himax_assigned_fw_name', 'himax_gpio_power_config',
                 'himax_ts_register_interrupt', 'himax_spi_read'):
        c += function(platform, name)
    c += function(common, 'himax_release_input') + TEST_MAIN
    src = tmp / 'regressions.c'
    src.write_text(c)
    binary = tmp / 'regressions'
    cc = os.environ.get('CC', 'cc')
    run([cc, '-std=gnu11', '-Wall', '-Wextra', '-Wno-unused-function',
         '-Wno-sign-compare', '-g', '-O1', '-fsanitize=address,undefined',
         '-fno-omit-frame-pointer', str(src), '-o', str(binary)])
    run([str(binary)], env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1'})
    if functions_only:
        print('Applied-tree source-contract checks NOT RUN in functions-only mode')
        return
    assert '.pm = &himax_common_pm_ops' in platform
    deinit = function(common, 'himax_chip_common_deinit')
    remove = function(platform, 'himax_chip_common_remove')
    assert 'kfree(ts);' not in deinit
    assert remove.index('himax_chip_common_deinit()') < remove.index('kfree(ts);')
    assert deinit.index('cancel_delayed_work_sync(&ts->work_boot_upgrade)') < deinit.index('himax_report_data_deinit()')
    assert deinit.index('himax_ts_unregister_interrupt()') < deinit.index('himax_release_input(ts)')
    assert 'ts->spi = NULL' not in remove
    assert 'return himax_chip_common_resume(ts);' in platform
    assert 'return himax_chip_common_suspend(ts);' in platform
    print('PASS: PM registration, error forwarding and teardown source contracts')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver-dir', type=Path,
                        help='test an already-applied driver directory only (no package/patch checks)')
    parser.add_argument('--functions-only', action='store_true', help='only C tests; requires --driver-dir and explicitly skips applied-tree contracts')
    args = parser.parse_args()
    if args.functions_only and not args.driver_dir:
        parser.error('--functions-only requires --driver-dir')
    with tempfile.TemporaryDirectory(prefix='gta4lwifi-check-') as temp:
        tmp = Path(temp)
        if args.driver_dir:
            print('Mode: supplied driver excerpts/tree; package/patch checks NOT RUN')
            driver_checks(args.driver_dir.resolve(), tmp, args.functions_only)
        else:
            check_sums()
            extract_added_files((PORT / '0002-fix-touch-node-and-port-himax-hx83102-spi-driver.patch').read_text(), tmp)
            run(['git', 'init', '-q', str(tmp)])
            run(['git', 'apply', '--check', '--include=' + PREFIX + '*', str(PORT / '0003-harden-himax-spi-lifecycle.patch')], cwd=tmp)
            run(['git', 'apply', '--include=' + PREFIX + '*', str(PORT / '0003-harden-himax-spi-lifecycle.patch')], cwd=tmp)
            driver_checks(tmp / PREFIX, tmp)
    print('No kernel build, hardware, firmware authenticity or flash approval is implied.')


if __name__ == '__main__':
    main()
