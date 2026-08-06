"""Generate a raw framebuffer image for Kobo e-reader Hello World POC."""
import struct
from PIL import Image, ImageDraw, ImageFont

# Kobo Nia: 758x1024, but we'll also generate for other common sizes.
# The shell script on the Kobo will detect the actual framebuffer size.
WIDTH = 758
HEIGHT = 1024

# Create 8-bit grayscale image (white background)
img = Image.new("L", (WIDTH, HEIGHT), 255)
draw = ImageDraw.Draw(img)

# Use a large built-in font
try:
    font_large = ImageFont.truetype("arial.ttf", 60)
    font_small = ImageFont.truetype("arial.ttf", 24)
except OSError:
    font_large = ImageFont.load_default(size=60)
    font_small = ImageFont.load_default(size=24)

# Draw "Hello World" centered
text = "Hello World!"
bbox = draw.textbbox((0, 0), text, font=font_large)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
x = (WIDTH - tw) // 2
y = (HEIGHT - th) // 2 - 50
draw.text((x, y), text, fill=0, font=font_large)

# Draw subtitle
sub = "ebook-dash POC"
bbox2 = draw.textbbox((0, 0), sub, font=font_small)
sw = bbox2[2] - bbox2[0]
draw.text(((WIDTH - sw) // 2, y + th + 40), sub, fill=80, font=font_small)

# Draw a border
draw.rectangle([20, 20, WIDTH - 21, HEIGHT - 21], outline=0, width=3)

# Save as raw 8-bit grayscale
raw_8bpp = img.tobytes()
with open("kobo_hello_8bpp.raw", "wb") as f:
    f.write(raw_8bpp)

# Also generate 16-bit RGB565 version (for devices that use that format)
img_rgb = img.convert("RGB")
pixels = list(img_rgb.getdata())
rgb565_data = bytearray()
for r, g, b in pixels:
    val = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    rgb565_data.extend(struct.pack("<H", val))
with open("kobo_hello_16bpp.raw", "wb") as f:
    f.write(rgb565_data)

# Also generate 32-bit RGBA version
img_rgba = img.convert("RGBA")
with open("kobo_hello_32bpp.raw", "wb") as f:
    f.write(img_rgba.tobytes())

# Save a preview PNG
img.save("kobo_hello_preview.png")

print(f"Generated framebuffer images for {WIDTH}x{HEIGHT}:")
print(f"  8bpp:  {len(raw_8bpp):,} bytes")
print(f"  16bpp: {len(rgb565_data):,} bytes")
print(f"  32bpp: {len(img_rgba.tobytes()):,} bytes")
print(f"  Preview: kobo_hello_preview.png")
