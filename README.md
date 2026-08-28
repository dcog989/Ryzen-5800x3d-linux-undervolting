# Ryzen 5800X3D Linux Undervolting

A Python script to undervolt the Ryzen 5800X3D CPU. It is a Linux implementation of the [Ryzen 5800X3D PBO2 undervolting tool for Windows](https://github.com/PrimeO7/How-to-undervolt-AMD-RYZEN-5800X3D-Guide-with-PBO2-Tuner).

## Installation

Requirements: `dkms`, `git`, `build-essential`, Linux headers:

- `sudo apt install linux-headers-$(uname -r) # Debian / Ubuntu`
- `sudo pacman -S linux-headers # Arch`

### Install `ryzen_smu`

```sh
git clone https://github.com/amkillam/ryzen_smu.git
cd ryzen_smu
sudo make dkms-install
```

From AUR:

```sh
yay -S ryzen_smu-dkms-git
```

Reload the kernel module:

```sh
sudo modprobe ryzen_smu
```

### Load `ryzen_smu` on every boot

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
```

```sh
sudo systemctl status ryzen-undervolt.service # check service status
```

---

## Usage

Run `sudo python ruv.py -h` for help:

```sh
usage: ruv.py [-h] (-l | -o OFFSET [OFFSET ...] | -r) [-c CORECOUNT]

PBO Curve Optimizer utility for Ryzen 5800X3D

options:
  -h, --help            show this help message and exit
  -l, --list            List current curve offsets
  -o, --offset OFFSET [OFFSET ...]
                        Set curve offset. One value applies to all cores (e.g. -30),
                        or provide multiple values for per-core offsets
                        (e.g. -30 -20 -15 ...)
  -r, --reset           Reset all offsets to 0
  -c, --corecount CORECOUNT
                        Number of cores to iterate over. Defaults to 8.
```

Now you can query and write PBO curve offsets on the fly. On 5800X3D you have 8 cores (plus 8 virtual hyperthreading counterparts). To set all cores to -30 offset:

```sh
sudo python ruv.py -c 8 -o -30
```

will return:

```sh
Core 0 set to: -30 | Readback verify: -30
Core 1 set to: -30 | Readback verify: -30
Core 2 set to: -30 | Readback verify: -30
Core 3 set to: -30 | Readback verify: -30
Core 4 set to: -30 | Readback verify: -30
Core 5 set to: -30 | Readback verify: -30
Core 6 set to: -30 | Readback verify: -30
Core 7 set to: -30 | Readback verify: -30
```

You can also set per-core offsets by providing multiple values:

```sh
sudo python ruv.py -c 8 -o -30 -25 -20 -15 -10 -5 0 0
```

To list current offsets:

```sh
sudo python ruv.py -l -c 8
```

To reset all offsets to 0:

```sh
sudo python ruv.py -r
```

The script response indicates what values were stored in the registers.

> [!NOTE]
> Curve Optimizer offsets are limited to the -30..30 range. -30 is the practical undervolting limit for the 5800X3D, and the SMU will clamp anything past it back to -30. The ruv script rejects out-of-range values.
> All offsets reset on reboot, so install the tool as a service to re-apply them automatically.

### Verify after restart / sleep

```sh
cd ~/[path to]/Ryzen-5800x3d-linux-undervolting
sudo python ruv.py -l -c 8
```
