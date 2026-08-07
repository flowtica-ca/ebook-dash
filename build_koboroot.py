"""Build KoboRoot.tgz for Kobo weather + calendar dashboard.

Generates weather icons as PGM images, bundles with FBInk and fonts.
"""
import tarfile
import io
import os
import math


# ---------------------------------------------------------------------------
# Weather icon generation (80x80 PGM grayscale)
# ---------------------------------------------------------------------------
ICON_SIZE = 80
INK = 30  # near-black for e-ink contrast


def _blank(w, h, bg=255):
    return bytearray([bg] * (w * h))


def _px(buf, w, h, x, y, val):
    ix, iy = int(round(x)), int(round(y))
    if 0 <= ix < w and 0 <= iy < h:
        buf[iy * w + ix] = max(0, min(255, val))


def _circle(buf, w, h, cx, cy, r, val=INK):
    for y in range(max(0, int(cy - r - 2)), min(h, int(cy + r + 3))):
        for x in range(max(0, int(cx - r - 2)), min(w, int(cx + r + 3))):
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            if d <= r - 0.5:
                buf[y * w + x] = val
            elif d < r + 0.5:
                a = r + 0.5 - d
                buf[y * w + x] = int(buf[y * w + x] * (1 - a) + val * a)


def _line(buf, w, h, x0, y0, x1, y1, val=INK, thick=2):
    length = max(1, int(math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2) * 2))
    for i in range(length + 1):
        t = i / length
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        r = thick / 2
        for dy in range(int(-r) - 1, int(r) + 2):
            for dx in range(int(-r) - 1, int(r) + 2):
                if dx * dx + dy * dy <= r * r:
                    _px(buf, w, h, x + dx, y + dy, val)


def _cloud(buf, w, h, cx, cy, scale=1.0):
    _circle(buf, w, h, cx - 12 * scale, cy + 2 * scale, 12 * scale, INK)
    _circle(buf, w, h, cx + 8 * scale, cy + 2 * scale, 14 * scale, INK)
    _circle(buf, w, h, cx - 2 * scale, cy - 6 * scale, 10 * scale, INK)
    _circle(buf, w, h, cx + 16 * scale, cy + 4 * scale, 8 * scale, INK)


def _to_pgm(buf, w, h):
    return f"P5\n{w} {h}\n255\n".encode() + bytes(buf)


def icon_sunny():
    s = ICON_SIZE
    buf = _blank(s, s)
    cx, cy = s // 2, s // 2
    _circle(buf, s, s, cx, cy, 14, INK)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x0 = cx + 20 * math.cos(rad)
        y0 = cy + 20 * math.sin(rad)
        x1 = cx + 32 * math.cos(rad)
        y1 = cy + 32 * math.sin(rad)
        _line(buf, s, s, x0, y0, x1, y1, INK, 3)
    return _to_pgm(buf, s, s)


def icon_cloudy():
    s = ICON_SIZE
    buf = _blank(s, s)
    _cloud(buf, s, s, s // 2, s // 2, 1.3)
    return _to_pgm(buf, s, s)


def icon_partly_cloudy():
    s = ICON_SIZE
    buf = _blank(s, s)
    cx, cy = s // 2 + 10, s // 2 - 10
    _circle(buf, s, s, cx, cy, 10, INK)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        _line(buf, s, s, cx + 14 * math.cos(rad), cy + 14 * math.sin(rad),
              cx + 22 * math.cos(rad), cy + 22 * math.sin(rad), INK, 2)
    _cloud(buf, s, s, s // 2 - 5, s // 2 + 8, 1.1)
    return _to_pgm(buf, s, s)


def icon_rain():
    s = ICON_SIZE
    buf = _blank(s, s)
    _cloud(buf, s, s, s // 2, s // 2 - 8, 1.2)
    for x_off in [-14, 0, 14]:
        _line(buf, s, s, s // 2 + x_off, s // 2 + 18,
              s // 2 + x_off - 4, s // 2 + 32, INK, 2)
    return _to_pgm(buf, s, s)


def icon_snow():
    s = ICON_SIZE
    buf = _blank(s, s)
    _cloud(buf, s, s, s // 2, s // 2 - 8, 1.2)
    for x_off in [-16, -4, 8, 20]:
        for y_off in [20, 30]:
            _circle(buf, s, s, s // 2 + x_off, s // 2 + y_off, 2, INK)
    return _to_pgm(buf, s, s)


def icon_thunder():
    s = ICON_SIZE
    buf = _blank(s, s)
    _cloud(buf, s, s, s // 2, s // 2 - 10, 1.2)
    bx = s // 2
    by = s // 2 + 12
    _line(buf, s, s, bx, by, bx - 6, by + 10, INK, 3)
    _line(buf, s, s, bx - 6, by + 10, bx + 2, by + 10, INK, 3)
    _line(buf, s, s, bx + 2, by + 10, bx - 4, by + 24, INK, 3)
    return _to_pgm(buf, s, s)


ICONS = {
    "sunny": icon_sunny,
    "cloudy": icon_cloudy,
    "partly_cloudy": icon_partly_cloudy,
    "rain": icon_rain,
    "snow": icon_snow,
    "thunder": icon_thunder,
}


# ---------------------------------------------------------------------------
# Shell script
# ---------------------------------------------------------------------------
DISPLAY_SCRIPT = r"""#!/bin/sh
# ebook-dash: weather + calendar dashboard with icons

FBINK="/usr/local/ebook-dash/fbink"
FONT="/usr/local/ebook-dash/NotoSans-Regular.ttf"
FONTB="/usr/local/ebook-dash/NotoSans-Bold.ttf"
ICONS="/usr/local/ebook-dash/icons"
LOCKFILE="/tmp/ebook-dash.lock"
DISABLE="/mnt/onboard/.kobo/ebook-dash-disable"
LOG="/mnt/onboard/.kobo/ebookdash.log"
LOCATION="Kingston+Ontario"
CAL_URL_OFIR="https://script.google.com/macros/s/AKfycbwqESigr8ptwkFdigeTRWFy0SBPKOLtI0Uhl1fkrIcpRiqaCOiZ5I9BBDyBahNaqP4/exec"
CAL_URL_JENNY="https://script.google.com/macros/s/AKfycbxcmgtJ6NLtgYMn2cPbM21u9s0uY9mhnXeoBIfY7LYQAxUuF30_jsOO-CaJVuPANaSW/exec"

[ -f "$LOCKFILE" ] && exit 0
touch "$LOCKFILE"
trap "rm -f $LOCKFILE" EXIT INT TERM

TRIES=0
while [ ! -d /mnt/onboard/.kobo ] && [ $TRIES -lt 60 ]; do
    sleep 1
    TRIES=$((TRIES + 1))
done

[ -f "$DISABLE" ] && exit 0

echo "=== ebook-dash ===" > "$LOG"
chmod +x "$FBINK" 2>/dev/null

sleep 20
[ -f "$DISABLE" ] && exit 0

echo "ebook-dash" > /sys/power/wake_lock 2>/dev/null

ensure_wifi() {
    iwconfig wlan0 power off 2>/dev/null
    if ! ifconfig wlan0 2>/dev/null | grep -q "inet addr"; then
        echo "WiFi down, reconnecting..." >> "$LOG"
        ifconfig wlan0 up 2>/dev/null
        wpa_cli -i wlan0 reassociate 2>/dev/null
        sleep 3
        udhcpc -i wlan0 -t 3 -T 2 -q 2>/dev/null
    fi
}

ensure_wifi

ttbox() {
    _SZ="$1"; _TP="$2"; _BT="$3"; _LF="$4"; _RT="$5"; _TX="$6"; _ST="${7:-regular}"
    if [ "$_ST" = "bold" ]; then
        $FBINK -t "bold=$FONTB,size=$_SZ,top=$_TP,left=$_LF,bottom=$_BT,right=$_RT" -b -q "$_TX" 2>> "$LOG"
    else
        $FBINK -t "regular=$FONT,size=$_SZ,top=$_TP,left=$_LF,bottom=$_BT,right=$_RT" -b -q "$_TX" 2>> "$LOG"
    fi
}

WEATHER_FILE="/tmp/weather.json"

parse_weather() {
    _FIELD="$1"; _OCCUR="${2:-1}"
    grep -o "\"${_FIELD}\": *\"[^\"]*\"" "$WEATHER_FILE" | sed -n "${_OCCUR}p" | sed 's/.*: *"//;s/"//'
}

weather_icon() {
    case "$1" in
        113) echo "sunny";;
        116) echo "partly_cloudy";;
        119|122) echo "cloudy";;
        143|248) echo "cloudy";;
        176|263|266|293|296|299|302|305|308|353|356|359) echo "rain";;
        200|386|389|392|395) echo "thunder";;
        227|230|323|326|329|332|335|338|368|371|374|377) echo "snow";;
        *) echo "cloudy";;
    esac
}

fetch_weather() {
    if wget -q -T 15 -O "$WEATHER_FILE" "http://wttr.in/${LOCATION}?format=j1" 2>> "$LOG"; then
        TEMP=$(parse_weather "temp_C" 1)
        FEELS=$(parse_weather "FeelsLikeC" 1)
        HUMID=$(parse_weather "humidity" 1)
        WINDSP=$(parse_weather "windspeedKmph" 1)
        WINDDIR=$(parse_weather "winddir16Point" 1)
        WCODE=$(parse_weather "weatherCode" 1)
        DESC=$(grep -A 3 '"weatherDesc"' "$WEATHER_FILE" | grep '"value"' | head -1 | sed 's/.*"value": *"//;s/".*//')
        WICON=$(weather_icon "$WCODE")
        MAXT1=$(parse_weather "maxtempC" 1)
        MINT1=$(parse_weather "mintempC" 1)
        MAXT2=$(parse_weather "maxtempC" 2)
        MINT2=$(parse_weather "mintempC" 2)
        MAXT3=$(parse_weather "maxtempC" 3)
        MINT3=$(parse_weather "mintempC" 3)
        _DOW=$(date '+%w')
        case $(( (_DOW + 2) % 7 )) in
            0) DAY3="Sun";; 1) DAY3="Mon";; 2) DAY3="Tue";;
            3) DAY3="Wed";; 4) DAY3="Thu";; 5) DAY3="Fri";; 6) DAY3="Sat";;
        esac
        echo "Weather: ${TEMP}C ${DESC} code=${WCODE} icon=${WICON}" >> "$LOG"
    else
        echo "Weather fetch failed" >> "$LOG"
    fi
}

fetch_https() {
    _URL="$1"
    if command -v curl > /dev/null 2>&1; then
        curl -s -k -L -m 15 "$_URL" 2>> "$LOG"
        return
    fi
    if command -v openssl > /dev/null 2>&1; then
        _HOST=$(echo "$_URL" | sed 's|https://||;s|/.*||')
        _PATH=$(echo "$_URL" | sed "s|https://${_HOST}||")
        _TRIES=0
        while [ $_TRIES -lt 5 ]; do
            _RESP=$(printf "GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n" "$_PATH" "$_HOST" | \
                timeout 15 openssl s_client -connect "${_HOST}:443" -quiet 2>/dev/null)
            [ -z "$_RESP" ] && return
            _LOC=$(echo "$_RESP" | grep -i "^Location:" | sed 's/^[Ll]ocation: *//;s/\r//')
            if [ -n "$_LOC" ]; then
                _HOST=$(echo "$_LOC" | sed 's|https://||;s|/.*||')
                _PATH=$(echo "$_LOC" | sed "s|https://${_HOST}||")
                _TRIES=$((_TRIES + 1))
            else
                echo "$_RESP" | sed '1,/^\r$/d' | tr -d '\r' | sed '/^[0-9a-fA-F]*$/d' | sed '/^$/d'
                return
            fi
        done
    fi
    wget -q -T 15 -O - "$_URL" 2>> "$LOG"
}

parse_cal() {
    _DATA="$1"
    if [ -z "$_DATA" ]; then
        echo "No data"
        return
    fi
    if echo "$_DATA" | grep -q "^NONE"; then
        echo "No events"
    else
        echo "$_DATA" | tr -cd '\11\12\40-\176' | sed 's/^TODAY|/Today  /;s/^TMRW|/Tmrw   /;s/|/  /'
    fi
}

fetch_calendars() {
    _TS=$(date +%s)
    _OFIR=$(fetch_https "${CAL_URL_OFIR}?t=${_TS}")
    echo "Cal Ofir: $_OFIR" >> "$LOG"
    [ -n "$_OFIR" ] && CAL_OFIR=$(parse_cal "$_OFIR")

    _JENNY=$(fetch_https "${CAL_URL_JENNY}?t=${_TS}")
    echo "Cal Jenny: $_JENNY" >> "$LOG"
    [ -n "$_JENNY" ] && CAL_JENNY=$(parse_cal "$_JENNY")
}

draw_dashboard() {
    echo "draw: $(date)" >> "$LOG"

    TIME_NOW=$(date '+%H:%M')
    DAY_NOW=$(date '+%A')
    DATE_NOW=$(date '+%B %d, %Y')
    UPDATE_TIME=$(date '+%H:%M')

    $FBINK -c -b -q 2>> "$LOG"

    # === TIME + DATE (full width, centered) ===
    ttbox 48 25 870 100 100 "$TIME_NOW" bold
    ttbox 16 150 830 100 100 "${DAY_NOW}, ${DATE_NOW}"

    # === WEATHER ICON + TEMPERATURE ===
    # Icon at left (rendered after text boxes)
    # Temperature next to icon
    ttbox 38 240 640 190 30 "${TEMP}C" bold
    ttbox 18 340 640 190 30 "${DESC}
Kingston, Ontario"

    # Render weather icon
    if [ -n "$WICON" ] && [ -f "${ICONS}/${WICON}.pgm" ]; then
        $FBINK -g file="${ICONS}/${WICON}.pgm",x=50,y=245 -b -q 2>> "$LOG"
    fi

    # === DETAILS ROW ===
    ttbox 12 435 554 30 500 "Feels Like"
    ttbox 18 460 524 30 500 "${FEELS}C" bold
    ttbox 12 435 554 270 260 "Humidity"
    ttbox 18 460 524 270 260 "${HUMID}%" bold
    ttbox 12 435 554 500 30 "Wind"
    ttbox 18 460 524 500 30 "${WINDSP}km/h ${WINDDIR}" bold

    # === FORECAST ===
    ttbox 14 520 470 30 30 "FORECAST" bold
    ttbox 14 555 310 30 30 "Today     ${MAXT1}/${MINT1}C
Tmrw      ${MAXT2}/${MINT2}C
${DAY3}       ${MAXT3}/${MINT3}C"

    # === CALENDARS (side by side) ===
    ttbox 16 700 290 30 390 "Ofir" bold
    ttbox 13 740 120 30 390 "$CAL_OFIR"

    ttbox 16 700 290 400 30 "Jenny" bold
    ttbox 13 740 120 400 30 "$CAL_JENNY"

    # === FOOTER ===
    ttbox 11 970 10 30 30 "Updated: ${UPDATE_TIME}  |  ebook-dash"

    $FBINK -s -f -W GC16 -q >> "$LOG" 2>&1
    echo "done: $(date)" >> "$LOG"
}

echo "Starting main loop" >> "$LOG"

TEMP="--"; FEELS="--"; HUMID="--"; WINDSP="--"; WINDDIR=""; DESC="No data"
WCODE=""; WICON="cloudy"
MAXT1="--"; MINT1="--"; MAXT2="--"; MINT2="--"; MAXT3="--"; MINT3="--"; DAY3=""
CAL_OFIR="Loading..."
CAL_JENNY="Loading..."
fetch_weather
fetch_calendars
draw_dashboard

CYCLE=0
while true; do
    sleep 60
    [ -f "$DISABLE" ] && exit 0
    CYCLE=$((CYCLE + 1))
    if [ $((CYCLE % 5)) -eq 0 ]; then
        ensure_wifi
        fetch_weather
        fetch_calendars
    fi
    draw_dashboard
done
""".encode('utf-8')

UDEV_RULE = b"""# ebook-dash: start dashboard on boot
ACTION=="add", KERNEL=="fb0", RUN+="/bin/sh -c '/usr/local/ebook-dash/display.sh &'"
"""


def build_koboroot():
    tgz_path = "KoboRoot.tgz"
    with tarfile.open(tgz_path, "w:gz") as tar:
        add_dir(tar, "usr/local/ebook-dash")
        add_dir(tar, "usr/local/ebook-dash/icons")

        for name in ["fbink", "NotoSans-Regular.ttf", "NotoSans-Bold.ttf"]:
            with open(name, "rb") as f:
                data = f.read()
            mode = 0o755 if name == "fbink" else 0o644
            add_bytes(tar, f"usr/local/ebook-dash/{name}", data, mode)
            print(f"  Added {name} ({len(data):,} bytes)")

        for icon_name, gen_fn in ICONS.items():
            data = gen_fn()
            add_bytes(tar, f"usr/local/ebook-dash/icons/{icon_name}.pgm", data, 0o644)
            print(f"  Added icon {icon_name}.pgm ({len(data):,} bytes)")

        add_bytes(tar, "usr/local/ebook-dash/display.sh", DISPLAY_SCRIPT, 0o755)
        print("  Added display.sh")

        add_bytes(tar, "etc/udev/rules.d/98-ebook-dash.rules", UDEV_RULE, 0o644)
        print("  Added udev rule")

    size = os.path.getsize(tgz_path)
    print(f"\nBuilt {tgz_path} ({size:,} bytes / {size/1024:.0f} KB)")


def add_dir(tar, name):
    i = tarfile.TarInfo(name=name); i.type = tarfile.DIRTYPE; i.mode = 0o755; tar.addfile(i)

def add_bytes(tar, name, content, mode=0o644):
    i = tarfile.TarInfo(name=name); i.size = len(content); i.mode = mode
    tar.addfile(i, io.BytesIO(content))

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    build_koboroot()
