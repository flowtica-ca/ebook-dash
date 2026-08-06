"""Generate a weather + time dashboard image for Kobo e-reader.

Fetches weather from wttr.in, renders a clean e-ink-optimized dashboard
PNG at 758x1024 (Kobo Aura resolution). Also outputs raw BGRA framebuffer data.
"""
import json
import math
import urllib.request
import datetime
from PIL import Image, ImageDraw, ImageFont

WIDTH = 758
HEIGHT = 1024
LOCATION = "Kingston+Ontario"
DISPLAY_LOCATION = "Kingston, Ontario"

# Top offset to avoid Kobo's hidden bezel/status area
TOP_OFFSET = 40


def fetch_weather():
    url = f"https://wttr.in/{LOCATION}?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "ebook-dash/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def get_font(size):
    for path in ["arial.ttf", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def get_font_bold(size):
    for path in ["arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return get_font(size)


def draw_weather_icon(draw, x, y, size, code):
    code = int(code)
    cx, cy = x + size // 2, y + size // 2
    r = size // 3

    if code == 113:  # Sunny
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=60)
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            x1 = cx + int((r + 8) * math.cos(rad))
            y1 = cy + int((r + 8) * math.sin(rad))
            x2 = cx + int((r + 18) * math.cos(rad))
            y2 = cy + int((r + 18) * math.sin(rad))
            draw.line([(x1, y1), (x2, y2)], fill=60, width=3)
    elif code == 116:  # Partly cloudy
        draw.ellipse([cx - r - 10, cy - r, cx + r - 10, cy + r], fill=80)
        draw.ellipse([cx - 15, cy - 5, cx + r + 15, cy + r + 10], fill=120)
    elif code in (119, 122):  # Cloudy / Overcast
        draw.ellipse([cx - r - 5, cy - 5, cx + r - 5, cy + r + 5], fill=140)
        draw.ellipse([cx - 10, cy, cx + r + 10, cy + r + 10], fill=120)
        draw.ellipse([cx - r, cy + 5, cx + 5, cy + r + 15], fill=130)
    elif code in (176, 263, 266, 293, 296, 299, 302, 305, 308, 311, 314, 353, 356, 359):
        draw.ellipse([cx - r, cy - r, cx + r, cy + 5], fill=120)
        for i in range(-1, 2):
            lx = cx + i * 15
            draw.line([(lx, cy + 15), (lx - 5, cy + 30)], fill=80, width=2)
            draw.line([(lx, cy + 25), (lx - 5, cy + 40)], fill=80, width=2)
    elif code in (179, 182, 185, 227, 230, 317, 320, 323, 326, 329, 332, 335, 338,
                  362, 365, 368, 371, 374, 377, 392, 395):
        draw.ellipse([cx - r, cy - r, cx + r, cy + 5], fill=120)
        for i in range(-1, 2):
            lx = cx + i * 15
            draw.ellipse([lx - 3, cy + 15, lx + 3, cy + 21], fill=80)
            draw.ellipse([lx - 3, cy + 28, lx + 3, cy + 34], fill=80)
    else:
        draw.ellipse([cx - r, cy - r // 2, cx + r, cy + r // 2 + 10], fill=120)


def render_dashboard(weather_data):
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    now = datetime.datetime.now()
    current = weather_data["current_condition"][0]
    forecast_days = weather_data["weather"]

    temp_c = current["temp_C"]
    feels_like = current["FeelsLikeC"]
    humidity = current["humidity"]
    weather_desc = current["weatherDesc"][0]["value"]
    weather_code = current["weatherCode"]
    wind_kmph = current["windspeedKmph"]
    wind_dir = current["winddir16Point"]

    font_time = get_font_bold(90)
    font_date = get_font(26)
    font_temp = get_font_bold(68)
    font_label = get_font(22)
    font_value = get_font_bold(26)
    font_desc = get_font(24)
    font_forecast_day = get_font_bold(20)
    font_forecast_temp = get_font(20)
    font_section = get_font_bold(18)

    y = TOP_OFFSET

    # === TIME ===
    time_str = now.strftime("%H:%M")
    bbox = draw.textbbox((0, 0), time_str, font=font_time)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, y), time_str, fill=0, font=font_time)
    y += 105

    # === DATE ===
    date_str = now.strftime("%A, %B %d, %Y")
    bbox = draw.textbbox((0, 0), date_str, font=font_date)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, y), date_str, fill=40, font=font_date)
    y += 45

    draw.line([(40, y), (WIDTH - 40, y)], fill=180, width=2)
    y += 20

    # === CURRENT WEATHER ===
    draw_weather_icon(draw, 40, y, 100, weather_code)

    temp_str = f"{temp_c}\u00b0C"
    draw.text((160, y - 5), temp_str, fill=0, font=font_temp)
    draw.text((160, y + 70), weather_desc, fill=60, font=font_desc)
    draw.text((160, y + 100), DISPLAY_LOCATION, fill=100, font=font_label)
    y += 150

    draw.line([(40, y), (WIDTH - 40, y)], fill=180, width=2)
    y += 25

    # === DETAILS GRID ===
    details = [
        ("Feels Like", f"{feels_like}\u00b0C"),
        ("Humidity", f"{humidity}%"),
        ("Wind", f"{wind_kmph} km/h {wind_dir}"),
    ]
    col_width = (WIDTH - 80) // 3
    for i, (label, value) in enumerate(details):
        dx = 40 + i * col_width
        draw.text((dx, y), label, fill=100, font=font_label)
        draw.text((dx, y + 28), value, fill=0, font=font_value)
    y += 80

    draw.line([(40, y), (WIDTH - 40, y)], fill=180, width=2)
    y += 20

    # === 3-DAY FORECAST ===
    draw.text((40, y), "FORECAST", fill=80, font=font_section)
    y += 35

    forecast_width = (WIDTH - 80) // 3
    for i, day in enumerate(forecast_days[:3]):
        dx = 40 + i * forecast_width
        date_obj = datetime.datetime.strptime(day["date"], "%Y-%m-%d")
        if i == 0:
            day_name = "Today"
        elif i == 1:
            day_name = "Tomorrow"
        else:
            day_name = date_obj.strftime("%A")

        max_temp = day["maxtempC"]
        min_temp = day["mintempC"]
        desc = day["hourly"][4]["weatherDesc"][0]["value"]
        code = day["hourly"][4]["weatherCode"]

        draw.text((dx, y), day_name, fill=0, font=font_forecast_day)
        draw_weather_icon(draw, dx, y + 28, 60, code)
        draw.text((dx + 70, y + 35), f"{max_temp}\u00b0 / {min_temp}\u00b0", fill=40, font=font_forecast_temp)
        draw.text((dx + 70, y + 60), desc[:18], fill=80, font=font_forecast_temp)

    y += 120

    draw.line([(40, y), (WIDTH - 40, y)], fill=180, width=2)
    y += 25

    # === HOURLY FORECAST ===
    draw.text((40, y), "HOURLY", fill=80, font=font_section)
    y += 35

    today_hourly = forecast_days[0]["hourly"]
    current_hour = now.hour
    upcoming = []
    for h in today_hourly:
        hour = int(h["time"]) // 100
        if hour >= current_hour and len(upcoming) < 6:
            upcoming.append(h)
    if len(upcoming) < 6 and len(forecast_days) > 1:
        for h in forecast_days[1]["hourly"]:
            if len(upcoming) < 6:
                upcoming.append(h)

    if upcoming:
        hour_width = (WIDTH - 80) // min(6, len(upcoming))
        for i, h in enumerate(upcoming[:6]):
            dx = 40 + i * hour_width
            hour = int(h["time"]) // 100
            draw.text((dx, y), f"{hour:02d}:00", fill=80, font=font_forecast_temp)
            draw.text((dx, y + 25), f"{h['tempC']}\u00b0", fill=0, font=font_forecast_day)
            draw.text((dx, y + 50), f"{h['chanceofrain']}%\u2602", fill=100, font=font_forecast_temp)
    y += 90

    # === FOOTER ===
    draw.line([(40, y), (WIDTH - 40, y)], fill=180, width=2)
    y += 15
    update_str = f"Updated: {now.strftime('%H:%M:%S')}  |  ebook-dash"
    bbox = draw.textbbox((0, 0), update_str, font=font_label)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, y), update_str, fill=120, font=font_label)

    draw.rectangle([10, 10, WIDTH - 11, HEIGHT - 11], outline=0, width=2)

    return img


def save_raw(img):
    """Save raw BGRA framebuffer data for direct /dev/fb0 write."""
    STRIDE = 768
    img_rgba = img.convert("RGBA")
    pixels = img_rgba.load()
    raw = bytearray(STRIDE * 4 * HEIGHT)
    for y_row in range(HEIGHT):
        row_offset = y_row * STRIDE * 4
        for x_col in range(WIDTH):
            r, g, b, a = pixels[x_col, y_row]
            px_offset = row_offset + x_col * 4
            raw[px_offset] = b
            raw[px_offset + 1] = g
            raw[px_offset + 2] = r
            raw[px_offset + 3] = a
        for x_col in range(WIDTH, STRIDE):
            px_offset = row_offset + x_col * 4
            raw[px_offset] = 255
            raw[px_offset + 1] = 255
            raw[px_offset + 2] = 255
            raw[px_offset + 3] = 255
    with open("dashboard.raw", "wb") as f:
        f.write(raw)
    print(f"Saved dashboard.raw ({len(raw):,} bytes)")


def main():
    print("Fetching weather data...")
    try:
        weather = fetch_weather()
        print(f"Location: {DISPLAY_LOCATION}")
    except Exception as e:
        print(f"Error fetching weather: {e}")
        weather = None

    if weather:
        print("Rendering dashboard...")
        img = render_dashboard(weather)
    else:
        img = render_fallback()

    img.save("dashboard.png")
    print(f"Saved dashboard.png ({WIDTH}x{HEIGHT})")
    save_raw(img)
    return img


def render_fallback():
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    now = datetime.datetime.now()
    font_time = get_font_bold(96)
    font_date = get_font(32)

    time_str = now.strftime("%H:%M")
    bbox = draw.textbbox((0, 0), time_str, font=font_time)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, HEIGHT // 2 - 80), time_str, fill=0, font=font_time)

    date_str = now.strftime("%A, %B %d, %Y")
    bbox = draw.textbbox((0, 0), date_str, font=font_date)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, HEIGHT // 2 + 40), date_str, fill=40, font=font_date)
    draw.text((WIDTH // 2 - 100, HEIGHT // 2 + 100), "Weather unavailable", fill=120, font=font_date)
    draw.rectangle([10, 10, WIDTH - 11, HEIGHT - 11], outline=0, width=2)
    return img


if __name__ == "__main__":
    main()
