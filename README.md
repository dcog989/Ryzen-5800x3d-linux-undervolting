# Ryzen 5800X3D PBO2 Tune / Undervolt for Linux

A Python script to undervolt the Ryzen 5800X3D CPU. It is a Linux implementation of the [Windows PBO2 undervolting tool](https://github.com/PrimeO7/How-to-undervolt-AMD-RYZEN-5800X3D-Guide-with-PBO2-Tuner).

This is a modified fork of the unmaintained [svenlange2/Ryzen-5800x3d-Linux-undervolting](https://github.com/svenlange2/Ryzen-5800x3d-linux-undervolting) script. It addresses numerous issues:

- **Allows per-core offsets** — pass up to 8 values with `-o` to tune each core individually instead of one value for all cores
- **Readback verification** — every write is read back and compared; a mismatch (or read failure) is reported and exits non-zero
- **Safer offset decoding** — the reply is masked to the low 16 bits and sign-extended to match the write mask, so stray upper bits in that word cannot turn -30 into a large positive number
- **Hardened failure handling** — SMU command failures return `None`, I/O errors are caught and reported once at the SMU layer, and the script exits non-zero whenever any core fails
- **Input validation** — `--corecount` is validated to 1-8 and offsets to the hardware range of -30...30, with a warning on positive values
- **Cleaner CLI** — `-l`, `-o`, and `-r` are mutually exclusive, `--corecount` defaults to 8, and a `-o` value list is validated against the core count
- **Removed dead code** — dropped the broken SMU busy-wait polling that could spin forever when the driver runs commands synchronously

---

## Installation

Requires:

1. **`ryzen_smu`** — DKMS module (<https://github.com/amkillam/ryzen_smu>), a kernel driver that exposes the CPU's SMU.
2. **`ruv.py`** — this repo, which requires the DKMS module.

### Part 1: install the `ryzen_smu` kernel driver

[Install from source](https://github.com/amkillam/ryzen_smu), or the `ryzen_smu-dkms-git` AUR package.

Pick one method only: building it from source *and* installing the AUR package leaves two copies in DKMS.

### Part 2: install `ruv.py`

```sh
git clone https://github.com/dcog989/Ryzen-5800x3d-linux-undervolting.git
cd Ryzen-5800x3d-linux-undervolting
```

Install as a systemd service:

```sh
sudo tee /etc/systemd/system/ryzen-undervolt.service > /dev/null <<'EOF'
[Unit]
Description=Ryzen 5800X3D undervolt
After=multi-user.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 /[path to]/Ryzen-5800x3d-linux-undervolting/ruv.py -c 8 -o -15

[Install]
WantedBy=multi-user.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
EOF
```

> [!NOTE]
> `-15` is an example starting point. Replace it with the per-core values for your chip.

Enable the service:

```sh
sudo systemctl daemon-reload && sudo systemctl enable --now ryzen-undervolt.service
sudo systemctl start ryzen-undervolt.service
```

```sh
sudo systemctl status ryzen-undervolt.service # check service status
```

---

## Usage

```sh
python3 ruv.py -h # show help (no root needed)
sudo python3 ruv.py -l # list current offsets
sudo python3 ruv.py -c 8 -o -15 # set all cores to -15 offset
sudo python3 ruv.py -c 8 -o -30 -25 -20 -15 -10 -5 -5 -10 # set per-core offsets
sudo python3 ruv.py -r # reset all offsets to 0
```

The script response confirms what values were stored.

> [!NOTE]
> Curve Optimizer offsets are limited to -30...30 range and the `ruv.py` script rejects out-of-range values.
> All offsets reset on reboot, so the tool must be installed as a service to re-apply them automatically.
> **Start low.** Some 5800X3D samples can hold `-30` on all cores, others might become unstable. So, apply values, stress test, and keep what works for your CPU.
> A bad offset does not stop the machine from powering on: it shows up as crashes or errors under load, after the service has applied it.
> If that leaves the machine unusable, boot with `systemd.unit=rescue.target` on the kernel command line so the service never runs, then `systemctl disable ryzen-undervolt.service` in that shell. Offsets are gone after the next reboot.

### Verify after restart / sleep

```sh
cd ~/[path to]/Ryzen-5800x3d-linux-undervolting
sudo python3 ruv.py -l -c 8
```

---

## Tests

```sh
python3 -m unittest discover
```

No root and no driver needed: the SMU and `/proc/cpuinfo` are faked.

---

## License

[MIT License](LICENSE)
