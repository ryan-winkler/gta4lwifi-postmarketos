/* SPDX-License-Identifier: MIT
 * Static ARM64 boot-stage marker. No shell, networking, block-device access,
 * partition writes, resets, GPIO access, or firmware changes.
 */
#if !defined(__aarch64__)
#error This diagnostic init targets AArch64 only
#endif
static long call(long n, long a, long b, long c, long d, long e, long f)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x3 __asm__("x3") = d;
	register long x4 __asm__("x4") = e;
	register long x5 __asm__("x5") = f;
	__asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2),
			 "r"(x3), "r"(x4), "r"(x5) : "memory", "cc");
	return x0;
}

static void write_text(long fd, const char *text)
{
	unsigned long size = 0;
	while (text[size])
		size++;
	while (size) {
		long done = call(64, fd, (long)text, (long)size, 0, 0, 0);
		if (done == -4) /* EINTR */
			continue;
		if (done <= 0)
			break;
		text += done;
		size -= (unsigned long)done;
	}
}

static long open_write(const char *path)
{
	/* O_WRONLY | O_NOCTTY | O_NONBLOCK: diagnostics must not wait on a tty. */
	return call(56, -100, (long)path, 1 | 0400 | 04000, 0, 0, 0);
}

__attribute__((noreturn)) void _start(void)
{
	long console, kmsg;
	struct { long seconds, nanoseconds; } delay = { 30, 0 };

	if (call(172, 0, 0, 0, 0, 0, 0) != 1) {
		write_text(1, "GTA4LWIFI_DIAG_SELFTEST: not PID1; no mounts performed\n");
		call(93, 0, 0, 0, 0, 0, 0);
		for (;;) {}
	}

	/* The cpio includes a console node even when devtmpfs cannot mount. */
	console = open_write("/dev/console");
	write_text(console, "GTA4LWIFI_DIAG_INIT_ENTERED: static ARM64 PID1\n");
	call(40, (long)"devtmpfs", (long)"/dev", (long)"devtmpfs", 2, 0, 0);
	call(40, (long)"proc", (long)"/proc", (long)"proc", 15, 0, 0);
	call(40, (long)"sysfs", (long)"/sys", (long)"sysfs", 15, 0, 0);
	if (console < 0)
		console = open_write("/dev/console");
	kmsg = open_write("/dev/kmsg");
	write_text(kmsg, "<5>GTA4LWIFI_DIAG_INIT_ENTERED: static ARM64 PID1\n");
	write_text(console, "No rootfs mount or graphical session attempted.\n");
	for (;;) {
		call(101, (long)&delay, 0, 0, 0, 0, 0);
		write_text(kmsg, "<5>GTA4LWIFI_DIAG_ALIVE\n");
		write_text(console, "GTA4LWIFI_DIAG_ALIVE\n");
	}
}
