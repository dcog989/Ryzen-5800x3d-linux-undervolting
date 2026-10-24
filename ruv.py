#!/usr/bin/env python3
# ==========================================================
# Ryzen 5800X3D Linux Undervolting Script
# https://github.com/dcog989/Ryzen-5800x3d-linux-undervolting
# ==========================================================

import argparse
import fcntl
import os
import struct
import sys

FS_PATH = "/sys/kernel/ryzen_smu_drv/"
LOCK_PATH = "/run/ruv.lock"

VER_PATH = FS_PATH + "version"
SMU_ARGS = FS_PATH + "smu_args"
MP1_CMD = FS_PATH + "mp1_smu_cmd"

CPUINFO = "/proc/cpuinfo"
# Zen 3 Vermeer (incl. 5800X3D) is family 19h model 21h; other families take different SMU messages
CPU_FAMILY = 25
CPU_MODEL = 33

SMU_OP_SET_CO = 0x35
SMU_OP_RESET_CO = 0x36
SMU_OP_GET_CO = 0x48


def cpu_supported():
    fields = {}
    with open(CPUINFO) as fp:
        for line in fp:
            key, sep, value = line.partition(":")
            if sep and key.strip() in ("cpu family", "model"):
                fields[key.strip()] = value.strip()
    family = fields.get("cpu family")
    model = fields.get("model")
    return family == str(CPU_FAMILY) and model == str(CPU_MODEL)


def read_file(file, size):
    with open(file, "rb") as fp:
        return fp.read(size)


def write_file(file, data):
    with open(file, "wb") as fp:
        return fp.write(data)


def read_file32(file):
    result = read_file(file, 4)
    if len(result) < 4:
        return None
    return struct.unpack("<I", result)[0]


def write_file32(file, value):
    return write_file(file, struct.pack("<I", value)) == 4


def read_file192(file):
    result = read_file(file, 24)
    if len(result) < 24:
        return None
    return struct.unpack("<IIIIII", result)


def write_file192(file, *values):
    return write_file(file, struct.pack("<IIIIII", *values)) == 24


def smu_command(op, arg1=0):
    try:
        # The driver takes six argument words; these commands use only the first
        if not write_file192(SMU_ARGS, arg1, 0, 0, 0, 0, 0):
            print("Failed to write SMU arguments")
            return None

        # The driver executes the command synchronously inside this write and
        # stores the return code (SMU_Return_OK == 1) in mp1_smu_cmd.
        if not write_file32(MP1_CMD, op):
            print(f"Failed to execute the SMU command: {op:08X}")
            return None

        status = read_file32(MP1_CMD)
        args = read_file192(SMU_ARGS)
    except OSError as e:
        print(f"SMU command {op:#04x} failed: {e}")
        return None

    if status is None:
        print("Failed to read SMU status.")
        return None

    if status != 1:
        print(f"SMU Command Result Failed. Status code: {status}")
        return None

    if args is None:
        print("Failed to read SMU response arguments")
        return None

    return args


# Core index goes in bits 20-23; the 5800X3D has one CCD, so core_id fits as-is
def get_core_offset(core_id):
    result = smu_command(SMU_OP_GET_CO, core_id << 20)
    if result:
        value = result[0] & 0xFFFF
        if value >= 0x8000:
            value -= 0x10000
        return value
    return None


def set_core_offset(core_id, value):
    result = smu_command(SMU_OP_SET_CO, (core_id << 20) | (value & 0xFFFF))
    return result is not None


def main():
    parser = argparse.ArgumentParser(
        description="PBO Curve Optimizer utility for Ryzen 5800X3D"
    )

    # Mutually exclusive group: user must choose List, Offset, or Reset (cannot mix)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "-l", "--list", action="store_true", help="List current curve offsets"
    )
    action_group.add_argument(
        "-o",
        "--offset",
        nargs="+",
        type=int,
        help="Set curve offset. One value applies to all cores (e.g. -30), or provide multiple values for per-core offsets (e.g. -30 -20 -15...)",
    )
    action_group.add_argument(
        "-r",
        "--reset",
        action="store_true",
        help="Reset all offsets to 0, then verify the first --corecount cores",
    )

    parser.add_argument(
        "-c",
        "--corecount",
        default=8,
        type=int,
        help="Number of cores to iterate over. Defaults to 8.",
    )

    args = parser.parse_args()
    cc = args.corecount
    if not 1 <= cc <= 8:
        parser.error("--corecount must be between 1 and 8 (5800X3D has 8 cores).")

    # Checked after parsing so -h works without root or the driver
    if os.geteuid() != 0:
        print("Script must be run with root privileges.")
        sys.exit(1)

    if not cpu_supported():
        print(
            f"This tool only supports Zen 3 Vermeer CPUs "
            f"(family {CPU_FAMILY}, model {CPU_MODEL}, e.g. Ryzen 7 5800X3D)."
        )
        sys.exit(1)

    if not os.path.isfile(VER_PATH):
        print(f"The ryzen_smu driver doesn't seem to be loaded at {FS_PATH}")
        sys.exit(1)

    # One run at a time: the driver shares smu_args between processes, so two
    # interleaved runs would each undo part of the other. The fd stays open, so
    # the lock is held until the process exits. Fail fast rather than wait, so a
    # stuck holder never leaves this run hanging with no output.
    try:
        fcntl.flock(
            os.open(LOCK_PATH, os.O_WRONLY | os.O_CREAT, 0o644),
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )
    except BlockingIOError:
        print("Another ruv.py run is in progress; nothing was changed.")
        sys.exit(1)
    except OSError as e:
        print(f"Cannot lock {LOCK_PATH}: {e}")
        sys.exit(1)

    # 1. LIST
    if args.list:
        failed = 0
        for c in range(cc):
            offset = get_core_offset(c)
            if offset is None:
                failed += 1
            print(f"Core {c}: {offset if offset is not None else 'Error reading'}")
        if failed:
            sys.exit(1)
        sys.exit(0)

    # 2. RESET
    elif args.reset:
        if smu_command(SMU_OP_RESET_CO) is None:
            print("Failed to reset offsets.")
            sys.exit(1)

        failed = 0
        for c in range(cc):
            offset = get_core_offset(c)
            if offset != 0:
                print(
                    f"Core {c}: {offset if offset is not None else 'Error reading'}, expected 0"
                )
                failed += 1
        if failed:
            print("Failed to reset offsets.")
            sys.exit(1)

        print(f"Reset sent; cores 0-{cc - 1} read back 0.")
        sys.exit(0)

    # 3. SET OFFSETS
    elif args.offset is not None:
        # Validate that hardware limits are respected for all inputted offsets
        if not all(-30 <= x <= 30 for x in args.offset):
            print(
                "Error: Hardware limit for Curve Optimizer offsets is between -30 and 30."
            )
            sys.exit(1)

        if any(x > 0 for x in args.offset):
            print(
                "Warning: One or more offsets are positive. Undervolting usually requires negative values."
            )

        # Determine if applying a single offset to all, or per-core offsets
        if len(args.offset) == 1:
            offsets_to_apply = [args.offset[0]] * cc
        elif len(args.offset) == cc:
            offsets_to_apply = args.offset
        else:
            print(
                f"Error: You must provide either 1 offset (applied to all) or exactly {cc} offsets."
            )
            sys.exit(1)

        # Snapshot current offsets so a partial apply can be undone. A partial
        # snapshot cannot be restored faithfully, so refuse to write at all.
        previous = [get_core_offset(c) for c in range(cc)]
        if None in previous:
            print("Error: failed to read current offsets; nothing was applied.")
            sys.exit(1)

        # Apply offsets; a failure or Ctrl-C rolls every core back to the snapshot
        failed = 0
        try:
            for c, val in enumerate(offsets_to_apply):
                if set_core_offset(c, val):
                    readback = get_core_offset(c)
                    if readback is None:
                        print(
                            f"Core {c} set to: {val} | Readback verify: Error reading"
                        )
                        failed += 1
                    elif readback != val:
                        print(
                            f"Core {c} set to: {val} | Readback verify: MISMATCH, got {readback}"
                        )
                        failed += 1
                    else:
                        print(f"Core {c} set to: {val} | Readback verify: {readback}")
                else:
                    print(f"Core {c}: failed to set offset")
                    failed += 1
        except KeyboardInterrupt:
            print("Interrupted; restoring previous offsets.")
            failed += 1

        if failed:
            for c, prev in enumerate(previous):
                if not set_core_offset(c, prev):
                    print(f"Core {c}: failed to restore previous offset")
            print("Apply failed; restored previous offsets where possible.")
            sys.exit(1)


if __name__ == "__main__":
    main()
