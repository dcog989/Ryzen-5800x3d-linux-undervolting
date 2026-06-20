# Ryzen 5800X3D Linux Undervolting

A Python script to use Ryzen SMU for Linux PBO tuning / undervolting of Ryzen 5800X3D CPU.

## What is it?

This is a Linux implementation of the PBO2 undervolting tool used to [undervolt Ryzen CPUs in Windows](https://github.com/PrimeO7/How-to-undervolt-AMD-RYZEN-5800X3D-Guide-with-PBO2-Tuner).

## How to use it?

1. Clone <https://GitHub.com/leogx9r/ryzen_smu> repository then install the Ryzen SMU driver to enable communication with the Ryzen SMU (System Management Unit):

```sh
git clone https://github.com/leogx9r/ryzen_smu
cd ryzen_smu
sudo make dkms-install
```

Or install from AUR:

```sh
paru -S ryzen_smu-dkms-git
```

Now reboot. The `dkms-install` should make a new module in your system called `ryzen_smu`. It will autostart next time you reboot your system. Without it, the provided Python script will not function.

2. When you have the driver installed and functioning, clone this repository and start the undervolting tool:

```sh
git clone https://github.com/svenlange2/Ryzen-5800x3d-linux-undervolting.git
cd Ryzen-5800x3d-linux-undervolting
sudo python3 ruv.py
```

You should see this output:

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

3. Now you can query and write PBO curve offsets on the fly. On 5800X3D you have 8 cores (plus 8 virtual hyperthreading counterparts). To set all cores to -30 offset:

```sh
sudo python3 ruv.py -c 8 -o -30
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
sudo python3 ruv.py -c 8 -o -30 -25 -20 -15 -10 -5 0 0
```

To list current offsets:

```sh
sudo python3 ruv.py -l -c 8
```

To reset all offsets to 0:

```sh
sudo python3 ruv.py -r
```

The script response indicates what values were stored in the registers.

> [!NOTE]
> -30 appears to be a hard limit for the 5800X3D, so even if you exceed that it will reset back to -30.
> All offsets will reset on reboot so install this commandline as a service to automate things at reboots.

---

## Create persistent service

Switch `fresh` for your preferred terminal editor:

```sh
sudo fresh /etc/systemd/system/ryzen-undervolt.service
```

Add this to the service:

```ini
[Unit]
Description=Ryzen 5800X3D undervolt
After=multi-user.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /[path to]/Ryzen-5800x3d-linux-undervolting/ruv.py -c 8 -o -30
User=root

[Install]
WantedBy=multi-user.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target

```

### Enable service

```sh
sudo systemctl daemon-reload
sudo systemctl enable ryzen-undervolt.service
sudo systemctl start ryzen-undervolt.service
sudo systemctl status ryzen-undervolt.service
```

### Verify after restart / sleep

```sh
cd ~/[path to]/Ryzen-5800x3d-linux-undervolting
sudo python3 ruv.py -l -c 8
```
