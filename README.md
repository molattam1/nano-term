# Nano-Term

## Pi Zero 2W + GMT147SPI 1.47" TFT — Standalone Handheld Terminal

### Goal
Transform a 1.47" SPI TFT display (ST7789V3, 172×320) into a **standalone Linux Terminal**. Unlike mirror-based solutions, this uses a custom user-space driver to handle terminal emulation and **direct USB/Wireless keyboard input**, bypassing the need for an HDMI dummy plug or complex framebuffer hacks.

### Hardware
| Component | Details |
| :--- | :--- |
| **SBC** | Raspberry Pi Zero 2W (Quad-core ARM A53, 512MB RAM) |
| **Display** | GMT147SPI — 1.47" IPS TFT (172×320 pixels), ST7789V3 driver |
| **Input** | USB HID Keyboard or 2.4GHz Wireless Mini-Keyboard |
| **Power** | 5V Micro-USB (Pi) / 3.3V Logic (Display) |

### Wiring
Connect the display to the Pi Zero 2W 40-pin GPIO header:
| Display Pin | Function | Pi Physical Pin | Pi GPIO |
| :--- | :--- | :--- | :--- |
| **VCC** | Power (3.3V) | Pin 1 | 3.3V |
| **GND** | Ground | Pin 6 | GND |
| **SCL** | SPI Clock | Pin 23 | GPIO 11 (SCLK) |
| **SDA** | SPI Data (MOSI) | Pin 19 | GPIO 10 (MOSI) |
| **CS** | Chip Select | Pin 24 | GPIO 8 (CE0) |
| **DC** | Data/Command | Pin 18 | GPIO 24 |
| **RST** | Reset | Pin 22 | GPIO 25 |
| **BL** | Backlight | Pin 12 | GPIO 18 |

---

### Software Setup

#### Step 1: System Preparation
Flash **Raspberry Pi OS Lite (64-bit or 32-bit)** and enable SPI.
```bash
sudo raspi-config nonint do_spi 0
sudo apt update && sudo apt upgrade -y
```

#### Step 2: Install Core Dependencies
We use `pyte` for VT100 emulation and `evdev` for raw keyboard handling.
```bash
sudo apt install -y python3-spidev python3-pil python3-evdev python3-pip python3-gpiod
pip3 install pyte --break-system-packages
```

#### Step 3: Deploy the Terminal Engine
Create the main script `spi_terminal.py` in your home directory. This script handles the PTY (Pseudo-Terminal), the font rendering, and the ST7789 SPI protocol.
```bash
git clone https://github.com/molattam1/nano-term.git nano-term
```

#### Step 4: Configure Display Offsets
Because the ST7789 chip is 240px wide but the glass is only 172px, we apply a software offset in the `send_image` function:
* **Landscape Width:** 320px
* **Landscape Height:** 172px
* **Memory Offset:** 34px (Calculated as `(240 - 172) / 2`)

#### Step 5: Automate on Boot (Systemd)
Create a service so the terminal starts immediately on power-up:
```bash
sudo nano /etc/systemd/system/nano-term.service
```
Paste the following:
```ini
[Unit]
Description=Nano-Term SPI Terminal
After=multi-user.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/finch
ExecStart=/usr/bin/python3 /home/finch/nano-term/main.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```
Enable the service:
```bash
sudo systemctl enable nano-term.service
sudo systemctl start nano-term.service
```

---

### Key Technical Features

* **PTY Forking:** The script forks a `bash` process into a virtual terminal. This allows you to run `ls`, `top`, or `nano` just like a real SSH session.
* **Ghost Keyboard Logic:** Input is handled via `evdev.grab()`. The script scans for any device with keyboard capabilities. If the keyboard is unplugged, the script continues to render the screen and re-attaches the keyboard automatically when re-plugged.
* **Landscape Rendering:** The screen is initialized in `0x70` (Landscape) mode for maximum horizontal space.

---

### Troubleshooting
| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| **Screen is White** | SPI or Reset wiring | Verify Pins 19, 23, and 22. Ensure SPI is enabled in `config.txt`. |
| **Keyboard No Response** | Wrong event ID | Run `ls /dev/input/by-id/` to ensure your keyboard is detected as an `-event-kbd`. |
| **Text is shifted** | Wrong Offset | Adjust `X_OFFSET = 34` in the script. Try `0` or `35` if 34 is slightly off. |
| **Freeze on Unplug** | Blocking I/O | Ensure the script uses the `Non-Blocking` version with `try/except` around `kbd.read()`. |

---

### Results
* **Standalone Operation:** No HDMI monitor required.
* **Auto-Login:** Boots directly into a functional Bash shell.
* **Input Resilience:** Supports 2.4GHz Wireless mini-keyboards with automatic reconnect.
