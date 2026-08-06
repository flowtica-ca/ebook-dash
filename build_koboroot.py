"""Build KoboRoot.tgz for Kobo dynamic weather dashboard.

Uses FBInk text rendering for fully dynamic updates.
Fetches weather from wttr.in, updates every 10 minutes.
"""
import tarfile
import io
import os

DISPLAY_SCRIPT = b"""#!/bin/sh
# ebook-dash dynamic weather dashboard
# Create /mnt/onboard/.kobo/ebook-dash-disable to stop

FBINK="/usr/local/ebook-dash/fbink"
LOCKFILE="/tmp/ebook-dash.lock"
DISABLE="/mnt/onboard/.kobo/ebook-dash-disable"
LOG="/mnt/onboard/.kobo/ebookdash.log"
LOCATION="Kingston+Ontario"
WEATHER_FILE="/tmp/weather.json"
INTERVAL=600

[ -f "$LOCKFILE" ] && exit 0
touch "$LOCKFILE"

# Wait for /mnt/onboard
TRIES=0
while [ ! -d /mnt/onboard/.kobo ] && [ $TRIES -lt 60 ]; do
    sleep 1
    TRIES=$((TRIES + 1))
done

[ -f "$DISABLE" ] && exit 0

echo "=== ebook-dash dynamic ===" > "$LOG"
echo "Started: $(date)" >> "$LOG"

chmod +x "$FBINK" 2>/dev/null

# Log inittab for debugging
cat /etc/inittab >> "$LOG" 2>&1

# Wait for Nickel to settle
sleep 25
[ -f "$DISABLE" ] && exit 0

# Parse a value from the weather JSON
# Usage: parse_weather "fieldName" [occurrence_number]
parse_weather() {
    FIELD="$1"
    OCCUR="${2:-1}"
    grep -o "\"${FIELD}\":\"[^\"]*\"" "$WEATHER_FILE" | sed -n "${OCCUR}p" | cut -d'"' -f4
}

draw_dashboard() {
    TIME_NOW=$(date '+%H:%M')
    DATE_NOW=$(date '+%A, %B %d %Y')

    # Fetch weather
    TEMP="" DESC="" FEELS="" HUMID="" WINDSP="" WINDDIR=""
    MAXT1="" MINT1="" MAXT2="" MINT2="" MAXT3="" MINT3=""

    if wget -q -T 10 -O "$WEATHER_FILE" "https://wttr.in/${LOCATION}?format=j1" 2>> "$LOG"; then
        TEMP=$(parse_weather "temp_C" 1)
        FEELS=$(parse_weather "FeelsLikeC" 1)
        HUMID=$(parse_weather "humidity" 1)
        WINDSP=$(parse_weather "windspeedKmph" 1)
        WINDDIR=$(parse_weather "winddir16Point" 1)
        DESC=$(grep -o '"weatherDesc":.{"value":"[^"]*"' "$WEATHER_FILE" | head -1 | sed 's/.*"value":"//;s/"//')
        MAXT1=$(parse_weather "maxtempC" 1)
        MINT1=$(parse_weather "mintempC" 1)
        MAXT2=$(parse_weather "maxtempC" 2)
        MINT2=$(parse_weather "mintempC" 2)
        MAXT3=$(parse_weather "maxtempC" 3)
        MINT3=$(parse_weather "mintempC" 3)
        echo "Weather OK: ${TEMP}C ${DESC}" >> "$LOG"
    else
        echo "Weather fetch failed" >> "$LOG"
        TEMP="--" FEELS="--" HUMID="--" WINDSP="--" WINDDIR=""
        DESC="No connection"
    fi

    # Draw everything with -b (batch/no refresh), then one final refresh
    # -V = ignore viewport corrections so we control exact placement

    # Clear screen (no refresh yet)
    $FBINK -k -b 2>> "$LOG"

    # Time (row 3 to avoid top bezel/status area)
    $FBINK -m -S 7 -y 3 -b "$TIME_NOW" 2>> "$LOG"

    # Date
    $FBINK -m -S 2 -y 8 -b "$DATE_NOW" 2>> "$LOG"

    # Separator
    $FBINK -m -S 1 -y 11 -b "--------------------------------------------" 2>> "$LOG"

    # Temperature + Description
    if [ "$TEMP" != "--" ]; then
        $FBINK -m -S 5 -y 12 -b "${TEMP}C - ${DESC}" 2>> "$LOG"
    else
        $FBINK -m -S 4 -y 12 -b "Weather Unavailable" 2>> "$LOG"
    fi

    # Location
    $FBINK -m -S 2 -y 17 -b "Kingston, Ontario" 2>> "$LOG"

    # Separator
    $FBINK -m -S 1 -y 20 -b "--------------------------------------------" 2>> "$LOG"

    # Details row
    $FBINK -S 2 -x 1 -y 22 -b "Feels: ${FEELS}C" 2>> "$LOG"
    $FBINK -S 2 -x 17 -y 22 -b "Humid: ${HUMID}%" 2>> "$LOG"
    $FBINK -S 2 -x 33 -y 22 -b "Wind: ${WINDSP}km/h" 2>> "$LOG"

    # Separator
    $FBINK -m -S 1 -y 25 -b "--------------------------------------------" 2>> "$LOG"

    # Forecast
    if [ -n "$MAXT1" ]; then
        $FBINK -S 1 -x 1 -y 27 -b "FORECAST" 2>> "$LOG"
        $FBINK -S 2 -x 1 -y 29 -b "Today: ${MAXT1}/${MINT1}C" 2>> "$LOG"
        $FBINK -S 2 -x 17 -y 29 -b "Tmrw: ${MAXT2}/${MINT2}C" 2>> "$LOG"
        $FBINK -S 2 -x 33 -y 29 -b "Sat: ${MAXT3}/${MINT3}C" 2>> "$LOG"
    fi

    # Separator
    $FBINK -m -S 1 -y 32 -b "--------------------------------------------" 2>> "$LOG"

    # Footer with update time
    UPDATE_TIME=$(date '+%H:%M:%S')
    $FBINK -m -S 1 -y 34 -b "Updated: ${UPDATE_TIME}  |  ebook-dash" 2>> "$LOG"

    # Single full-screen flash refresh
    $FBINK -s -f -W GC16 >> "$LOG" 2>&1

    echo "Dashboard drawn: $(date)" >> "$LOG"
}

# Main loop - draw immediately, then every 10 minutes
while true; do
    [ -f "$DISABLE" ] && exit 0

    draw_dashboard

    # Sleep 10 minutes, checking for disable every minute
    COUNT=0
    while [ $COUNT -lt 10 ]; do
        sleep 60
        [ -f "$DISABLE" ] && exit 0
        COUNT=$((COUNT + 1))
    done
done
"""

UDEV_RULE = b"""# ebook-dash: start dashboard on boot
ACTION=="add", KERNEL=="fb0", RUN+="/bin/sh -c '/usr/local/ebook-dash/display.sh &'"
"""


def build_koboroot():
    tgz_path = "KoboRoot.tgz"

    with tarfile.open(tgz_path, "w:gz") as tar:
        add_dir(tar, "usr/local/ebook-dash")

        with open("fbink", "rb") as f:
            data = f.read()
        add_bytes(tar, "usr/local/ebook-dash/fbink", data, 0o755)
        print(f"  Added fbink ({len(data):,} bytes)")

        add_bytes(tar, "usr/local/ebook-dash/display.sh", DISPLAY_SCRIPT, 0o755)
        print("  Added display.sh (dynamic, 10min loop)")

        add_bytes(tar, "etc/udev/rules.d/98-ebook-dash.rules", UDEV_RULE, 0o644)
        print("  Added udev rule")

    size = os.path.getsize(tgz_path)
    print(f"\nBuilt {tgz_path} ({size:,} bytes / {size/1024:.0f} KB)")


def add_dir(tar, name):
    info = tarfile.TarInfo(name=name)
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    tar.addfile(info)


def add_bytes(tar, name, content, mode=0o644):
    info = tarfile.TarInfo(name=name)
    info.size = len(content)
    info.mode = mode
    tar.addfile(info, io.BytesIO(content))


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("Building KoboRoot.tgz (dynamic dashboard)...")
    build_koboroot()
