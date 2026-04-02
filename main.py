cat > ~/spi_terminal.py << 'PYEOF'
#!/usr/bin/env python3
import spidev, time, gpiod, pyte, os, sys, select, signal, struct, fcntl, termios, pty, glob
from PIL import Image, ImageDraw, ImageFont
import evdev
from evdev import ecodes

# --- Configuration ---
# LANDSCAPE MODE: 320 is width, 172 is height
WIDTH, HEIGHT = 320, 172 
X_OFFSET = 34  # The internal memory offset for the 172px side
DC, RST, BL = 24, 25, 18
SPI_SPEED = 32000000

# --- Hardware Setup ---
chip = gpiod.Chip("/dev/gpiochip0")
cfg = {
    DC: gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT),
    RST: gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT),
    BL: gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT),
}
gpio = chip.request_lines(consumer="term", config=cfg)

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = SPI_SPEED
spi.mode = 0

def gs(p, v):
    gpio.set_value(p, gpiod.line.Value.ACTIVE if v else gpiod.line.Value.INACTIVE)

def cmd(c, d=None):
    gs(DC, 0)
    spi.xfer2([c])
    if d:
        gs(DC, 1)
        spi.xfer2(d)

def init_display():
    gs(BL, 1)
    gs(RST, 1); time.sleep(.05)
    gs(RST, 0); time.sleep(.05)
    gs(RST, 1); time.sleep(.15)
    
    cmd(0x01); time.sleep(.15) # Soft Reset
    cmd(0x11); time.sleep(.12) # Exit Sleep
    
    cmd(0x3A, [0x05])           # 16-bit color
    # 0x70 = Landscape Orientation (Rotated 90 deg)
    cmd(0x36, [0x70])           
    
    cmd(0x21)                   # Display Inversion On
    cmd(0x13)                   # Normal Mode
    cmd(0x29); time.sleep(.05) # Display On

def send_image(img):
    # Address Window for Landscape
    # X is 0-319, Y is Offset to Offset+171
    x_start, x_end = 0, WIDTH - 1
    y_start, y_end = X_OFFSET, X_OFFSET + HEIGHT - 1
    
    cmd(0x2A, [x_start >> 8, x_start & 0xFF, x_end >> 8, x_end & 0xFF])
    cmd(0x2B, [y_start >> 8, y_start & 0xFF, y_end >> 8, y_end & 0xFF])
    cmd(0x2C) # Write to RAM
    gs(DC, 1)
    
    rgb = img.convert("RGB")
    data = rgb.tobytes()
    raw = bytearray(WIDTH * HEIGHT * 2)
    for i in range(0, len(data), 3):
        r, g, b = data[i], data[i+1], data[i+2]
        c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        raw[(i//3)*2] = c >> 8
        raw[(i//3)*2+1] = c & 0xFF
    
    for i in range(0, len(raw), 4096):
        spi.xfer2(list(raw[i:i+4096]))

# --- Terminal Engine ---
# Increased font size slightly for landscape readability
FONT_SIZE = 14
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", FONT_SIZE)
bbox = font.getbbox("M")
fw, fh = bbox[2] - bbox[0], bbox[3] - bbox[1] + 4
cols, rows = WIDTH // fw, HEIGHT // fh

screen = pyte.Screen(cols, rows)
stream = pyte.Stream(screen)

# Colors
BG, FG = (0, 43, 54), (238, 232, 213)
CURSOR_COLOR = (133, 153, 0)

def render():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    
    for r_idx in range(rows):
        line = screen.buffer[r_idx]
        for c_idx in range(cols):
            char = line[c_idx]
            if char.data != " ":
                draw.text((c_idx * fw, r_idx * fh), char.data, font=font, fill=FG)
            
    cx, cy = screen.cursor.x * fw, screen.cursor.y * fh
    draw.rectangle([cx, cy, cx + fw, cy + fh], outline=CURSOR_COLOR, width=2)
    return img

# --- Keyboard Handling ---
def get_kbd():
    # Automatically finds the typing interface of the connected keyboard
    kbd_links = glob.glob("/dev/input/by-id/*-event-kbd")
    if kbd_links:
        return evdev.InputDevice(kbd_links[0])
    return None

kbd = get_kbd()
if kbd:
    try:
        kbd.grab() 
    except:
        pass

KEY_MAP = {
    'KEY_ENTER': b'\r', 'KEY_BACKSPACE': b'\x7f', 'KEY_TAB': b'\t',
    'KEY_SPACE': b' ', 'KEY_UP': b'\x1b[A', 'KEY_DOWN': b'\x1b[B',
    'KEY_RIGHT': b'\x1b[C', 'KEY_LEFT': b'\x1b[D'
}

# --- Process Setup (Shell) ---
master_fd, slave_fd = pty.openpty()
pid = os.fork()

if pid == 0:
    os.setsid()
    os.dup2(slave_fd, 0)
    os.dup2(slave_fd, 1)
    os.dup2(slave_fd, 2)
    os.close(master_fd)
    os.environ["TERM"] = "linux"
    os.environ["COLUMNS"] = str(cols)
    os.environ["LINES"] = str(rows)
    os.execvp("/bin/bash", ["/bin/bash"])

os.close(slave_fd)
init_display()
dirty = True

try:
    while True:
        inputs = [master_fd]
        if kbd: inputs.append(kbd.fd)
        
        r, _, _ = select.select(inputs, [], [], 0.02)
        
        if master_fd in r:
            try:
                data = os.read(master_fd, 1024)
                if data:
                    stream.feed(data.decode(errors='replace'))
                    dirty = True
            except OSError:
                break
            
        if kbd and kbd.fd in r:
            for event in kbd.read():
                if event.type == ecodes.EV_KEY and event.value == 1:
                    key_code = evdev.categorize(event).keycode
                    if isinstance(key_code, list): key_code = key_code[0]
                    
                    if key_code in KEY_MAP:
                        os.write(master_fd, KEY_MAP[key_code])
                    elif isinstance(key_code, str) and key_code.startswith('KEY_'):
                        char = key_code[4].lower()
                        if len(char) == 1:
                            os.write(master_fd, char.encode())
                    dirty = True

        if dirty:
            send_image(render())
            dirty = False

except KeyboardInterrupt:
    pass
finally:
    if kbd: 
        try: kbd.ungrab()
        except: pass
    spi.close()
    gpio.release()
PYEOF

sudo python3 ~/spi_terminal.py
