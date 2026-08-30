# Ryzen 5800X3D PBO2 Tune / Undervolt for Linux

A Python script to undervolt the Ryzen 5800X3D CPU. It is a Linux implementation of the [Windows PBO2 undervolting tool](https://github.com/PrimeO7/How-to-undervolt-AMD-RYZEN-5800X3D-Guide-with-PBO2-Tuner).

This is a modified fork of the unmaintained [svenlange2/Ryzen-5800x3d-Linux-undervolting](https://github.com/svenlange2/Ryzen-5800x3d-linux-undervolting) script. It addresses numerous issues:

- **Allows per-core offsets** — pass up to 8 values with `-o` to tune each core individually instead of one value for all cores
- **Readback verification** — every write is read back and compared; a mismatch (or read failure) is reported and exits non-zero
- **Correct offset decoding** — curve offsets are read as 16-bit signed values to match the write mask, so values below -15 no longer wrap to large positive numbers
- **Hardened failure handling** — SMU command failures return `None`, I/O errors are caught and reported once at the SMU layer, and the script exits non-zero whenever any core fails
- **Input validation** — `--corecount` is validated to 1-8 and offsets to the hardware range of -30...30, with a warning on positive values
- **Cleaner CLI** — `-l`, `-o`, and `-r` are mutually exclusive, `--corecount` defaults to 8, and a `-o` value list is validated against the core count
- **Removed dead code** — dropped the broken SMU busy-wait polling that could spin forever when the driver runs commands synchronously

---

## Installation

### a. Install from source

> [!NOTE]
> Requirements: `dkms`, `git`, `build-essential`, Linux headers.

Install Linux headers:

```sh
sudo apt install linux-headers-$(uname -r) # Debian / Ubuntu
sudo pacman -S linux-headers # Arch
```

```sh
git clone https://github.com/amkillam/ryzen_smu.git
cd ryzen_smu
sudo make dkms-install
```

### b. Install from AUR

```sh
yay -S ryzen_smu-dkms-git # or paru or other AUR helper
```

### Reload the kernel module

```sh
sudo modprobe ryzen_smu # enable the kernel module once installed
sudo dmesg | grep ryzen_smu # verify the module is loaded
```

### Load on every boot

```sh
echo 'ryzen_smu' | sudo tee /etc/modules-load.d/ryzen_smu.conf
```

### Clone the undervolting tool

```sh
git clone https://github.com/dcog989/Ryzen-5800x3d-linux-undervolting.git
cd Ryzen-5800x3d-linux-undervolting
```

### Create persistent service

```sh
sudo tee /etc/systemd/system/ryzen-undervolt.service > /dev/null <<'EOF'
[Unit]
Description=Ryzen 5800X3D undervolt
After=multi-user.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python /[path to]/Ryzen-5800x3d-linux-undervolting/ruv.py -c 8 -o -30

[Install]
WantedBy=multi-user.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
EOF
```

### Enable service

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
sudo python ruv.py -h # show help
sudo python ruv.py -l # list current offsets
sudo python ruv.py -c 8 -o -30 # set all cores to -30 offset
sudo python ruv.py -c 8 -o -30 -25 -20 -15 -10 -5 -5 -10 # set per-core offsets
sudo python ruv.py -r # reset all offsets to 0
```

The script response confirms what values were stored.

> [!NOTE]
> Curve Optimizer offsets are limited to -30...30 range. The SMU will clamp within that range and the `ruv.py` script rejects out-of-range values.
> All offsets reset on reboot, so the tool must be installed as a service to re-apply them automatically.

### Verify after restart / sleep

```sh
cd ~/[path to]/Ryzen-5800x3d-linux-undervolting
sudo python ruv.py -l -c 8
```
