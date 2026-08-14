"""Build KoboRoot.tgz for Kobo dynamic weather dashboard.

Uses FBInk TrueType rendering + wttr.in for weather data.
"""
import tarfile
import io
import os

DISPLAY_SCRIPT = r"""#!/bin/sh
# ebook-dash: two-panel weather + calendar dashboard
# Layout: time/date/weather on left, calendar on right

FBINK="/usr/local/ebook-dash/fbink"
FONT="/usr/local/ebook-dash/NotoSans-Regular.ttf"
FONTB="/usr/local/ebook-dash/NotoSans-Bold.ttf"
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

has_ip() {
    ifconfig wlan0 2>/dev/null | grep -q "inet addr"
}

wifi_state() {
    wpa_cli -i wlan0 status 2>/dev/null | sed -n 's/^wpa_state=//p'
}

# wlan0 loses its IP between almost every fetch cycle on this device, so
# this runs constantly rather than as a rare rescue. The previous fixed
# `sleep 3` was usually too short for WPA association to finish, leaving
# udhcpc to fire at an unassociated interface and burn its retries: the
# log showed 3 successes in 55 attempts. Poll for association instead,
# then run DHCP, and report which half failed.
# Worst case ~20s, well inside the 60s cycle.
ensure_wifi() {
    iwconfig wlan0 power off 2>/dev/null
    has_ip && return 0

    echo "WiFi down, reconnecting..." >> "$LOG"
    ifconfig wlan0 up 2>/dev/null
    wpa_cli -i wlan0 reassociate 2>/dev/null

    _ST=$(wifi_state)
    if [ -z "$_ST" ]; then
        # wpa_cli told us nothing to poll -- fall back to the old fixed wait
        # rather than refusing to try DHCP at all.
        sleep 3
    else
        _W=0
        while [ $_W -lt 12 ] && [ "$_ST" != "COMPLETED" ]; do
            sleep 1
            _W=$((_W + 1))
            _ST=$(wifi_state)
        done
        if [ "$_ST" != "COMPLETED" ]; then
            echo "WiFi assoc stuck at ${_ST} after ${_W}s" >> "$LOG"
            return 1
        fi
        echo "WiFi associated in ${_W}s" >> "$LOG"
    fi

    udhcpc -i wlan0 -t 4 -T 2 -n -q 2>/dev/null
    has_ip && return 0
    echo "WiFi associated but no DHCP lease" >> "$LOG"
    return 1
}

ensure_wifi

ttbox() {
    _SZ="$1"; _TP="$2"; _BT="$3"; _LF="$4"; _RT="$5"; _TX="$6"; _ST="${7:-regular}"
    if [ "$_ST" = "bold" ]; then
        $FBINK -t "bold=$FONTB,size=$_SZ,top=$_TP,left=$_LF,bottom=$_BT,right=$_RT" -b -q -- "$_TX" 2>> "$LOG"
    else
        $FBINK -t "regular=$FONT,size=$_SZ,top=$_TP,left=$_LF,bottom=$_BT,right=$_RT" -b -q -- "$_TX" 2>> "$LOG"
    fi
}

WEATHER_FILE="/tmp/weather.json"

parse_weather() {
    _FIELD="$1"; _OCCUR="${2:-1}"
    grep -o "\"${_FIELD}\": *\"[^\"]*\"" "$WEATHER_FILE" | sed -n "${_OCCUR}p" | sed 's/.*: *"//;s/"//'
}

check_online() {
    wget -q -T 5 -O /dev/null "http://wttr.in/?format=1" 2>/dev/null
}

# NotoSans has no weather glyphs, so conditions become plain words.
# A slot is 100px wide and the condition renders at size 11, so these stay
# at 5 characters or fewer — the widest, "Sunny", measures 64px, which
# leaves a clean gutter between slots. Anything that wraps gets dropped.
short_cond() {
    case "$1" in
        "")           echo "--";;
        *hunder*)     echo "Storm";;
        *lizzard*)    echo "Snow";;
        *Blowing*)    echo "Snow";;
        *leet*)       echo "Sleet";;
        *pellets*)    echo "Hail";;
        *now*)        echo "Snow";;
        *rizzle*)     echo "Drizl";;
        *ain*)        echo "Rain";;
        *hower*)      echo "Rain";;
        *vercast*)    echo "Ovcst";;
        *loudy*)      echo "Cloud";;
        *og*)         echo "Fog";;
        *ist*)        echo "Mist";;
        Sunny*)       echo "Sunny";;
        Clear*)       echo "Clear";;
        *)            echo "$1" | cut -d' ' -f1 | cut -c1-5;;
    esac
}

# wttr.in j1 gives 8 hourly entries per day (0,3,6,...,21) across 3 days.
# Flattened, entry N is the Nth occurrence of "time"/"tempC" in the file.
# "weatherDesc" is offset by one because current_condition carries one too.
#
# Called from draw_dashboard, not from fetch_weather: it only reads the
# local file, so the window keeps tracking the clock while the device is
# offline. Gating it on a successful fetch left the labels frozen at
# whatever period the last fetch happened in.
fetch_hourly() {
    [ -s "$WEATHER_FILE" ] || { reset_hourly; return; }

    # Pull each column out of the 39KB file once. This runs every draw, so
    # re-grepping the file per slot would be ~24 passes a minute.
    _DATES=$(grep -o '"date": *"[0-9-]*"' "$WEATHER_FILE" | sed 's/.*: *"//;s/"//')
    _TIMES=$(grep -o '"time": *"[0-9]*"' "$WEATHER_FILE" | sed 's/.*: *"//;s/"//')
    _TEMPS=$(grep -o '"tempC": *"[-0-9]*"' "$WEATHER_FILE" | sed 's/.*: *"//;s/"//')
    _DESCS=$(grep -A 3 '"weatherDesc"' "$WEATHER_FILE" | grep '"value"' | sed 's/.*"value": *"//;s/".*//')

    # After a long outage the file's day 1 is no longer today, and entry N
    # would point at the wrong day. Find which of its 3 days is today and
    # skip 8 entries per day; if none matches, the file is too old to use.
    _TODAY=$(date '+%Y-%m-%d')
    _DAYIDX=0
    _D=1
    while [ $_D -le 3 ]; do
        [ "$(echo "$_DATES" | sed -n "${_D}p")" = "$_TODAY" ] && { _DAYIDX=$_D; break; }
        _D=$((_D + 1))
    done
    if [ $_DAYIDX -eq 0 ]; then
        [ "$_LASTBASE" != "stale" ] && echo "Hourly: file has no entry for $_TODAY, blanking" >> "$LOG"
        _LASTBASE="stale"
        reset_hourly
        return
    fi

    _NOWH=$(date '+%H')
    _NOWH=${_NOWH#0}
    [ -z "$_NOWH" ] && _NOWH=0
    _BASE=$(( (_DAYIDX - 1) * 8 + _NOWH / 3 ))
    _I=0
    while [ $_I -lt 7 ]; do
        _N=$((_BASE + _I + 1))
        _RAWT=$(echo "$_TIMES" | sed -n "${_N}p")
        _RAWP=$(echo "$_TEMPS" | sed -n "${_N}p")
        _RAWD=$(echo "$_DESCS" | sed -n "$((_N + 1))p")
        if [ -n "$_RAWT" ]; then
            _LBL=$(printf '%02dh' $((_RAWT / 100)))
        else
            _LBL="--"
        fi
        [ -z "$_RAWP" ] && _RAWP="--"
        _SC=$(short_cond "$_RAWD")
        eval "H${_I}T=\"\$_LBL\""
        eval "H${_I}P=\"\$_RAWP\""
        eval "H${_I}C=\"\$_SC\""
        _I=$((_I + 1))
    done
    # Runs every draw now, so only log when the window actually shifts.
    if [ "$_LASTBASE" != "$_BASE" ]; then
        echo "Hourly: base=$_BASE ${H0T}/${H0P} ${H1T}/${H1P} ${H2T}/${H2P} ${H3T}/${H3P} ${H4T}/${H4P} ${H5T}/${H5P} ${H6T}/${H6P}" >> "$LOG"
        _LASTBASE="$_BASE"
    fi
}

reset_hourly() {
    _I=0
    while [ $_I -lt 7 ]; do
        eval "H${_I}T=\"--\""
        eval "H${_I}P=\"--\""
        eval "H${_I}C=\"\""
        _I=$((_I + 1))
    done
}

fetch_weather() {
    if wget -q -T 10 -O "$WEATHER_FILE" "http://wttr.in/${LOCATION}?format=j1" 2>> "$LOG"; then
        TEMP=$(parse_weather "temp_C" 1)
        FEELS=$(parse_weather "FeelsLikeC" 1)
        HUMID=$(parse_weather "humidity" 1)
        WINDSP=$(parse_weather "windspeedKmph" 1)
        DESC=$(grep -A 3 '"weatherDesc"' "$WEATHER_FILE" | grep '"value"' | head -1 | sed 's/.*"value": *"//;s/".*//')
        MAXT1=$(parse_weather "maxtempC" 1)
        MINT1=$(parse_weather "mintempC" 1)
        MAXT2=$(parse_weather "maxtempC" 2)
        MINT2=$(parse_weather "mintempC" 2)
        _DOW=$(date '+%w')
        case $(( (_DOW + 2) % 7 )) in
            0) DAY2="Sun";; 1) DAY2="Mon";; 2) DAY2="Tue";;
            3) DAY2="Wed";; 4) DAY2="Thu";; 5) DAY2="Fri";; 6) DAY2="Sat";;
        esac
        LAST_FETCH=$(date '+%H:%M')
        echo "Weather: ${TEMP}C ${DESC} feels=${FEELS} hum=${HUMID} wind=${WINDSP}" >> "$LOG"
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
                timeout 10 openssl s_client -connect "${_HOST}:443" -quiet 2>/dev/null)
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
    wget -q -T 10 -O - "$_URL" 2>> "$LOG"
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
    echo "ebook-dash" > /sys/power/wake_lock 2>/dev/null
    echo "draw: $(date)" >> "$LOG"

    TIME_NOW=$(date '+%H:%M')
    DAY_NOW=$(date '+%A')
    DATE_NOW=$(date '+%B %d, %Y')

    # Re-derive the hourly window from the clock on every draw, so it stays
    # correct even when the network is down and no fetch has succeeded.
    fetch_hourly

    $FBINK -c -b -q 2>> "$LOG"

    # === LEFT COLUMN ===

    ttbox 60 30 700 30 390 "${TEMP}°C" bold

    # Two-line capacity: 16 of wttr.in's 27 conditions fit one line here,
    # 8 more need two. The 3 longest still truncate, as they did on main.
    ttbox 24 240 610 30 390 "${DESC}" bold

    ttbox 16 414 490 30 390 "${DAY_NOW}, ${DATE_NOW}"

    # FBInk needs 3.375*size*lines + 6 px of box or it drops the lines that
    # do not fit (fitted to 14 on-device observations). At size 16 that is
    # 54px a line, so this block is merged to two lines and "Kingston, ON"
    # moved to the footer -- the four lines it used to take are 108px that
    # the hourly bar now occupies.
    ttbox 16 534 370 30 390 "Feels ${FEELS}°  Hum ${HUMID}%
Wind ${WINDSP}km/h"

    ttbox 16 654 250 30 390 "Tmrw  ${MAXT1}/${MINT1}°
${DAY2}   ${MAXT2}/${MINT2}°"

    # === RIGHT COLUMN ===
    # Ofir 30..398, Jenny 404..772 — equal 368px blocks

    ttbox 18 30 922 400 30 "Ofir" bold

    ttbox 14 102 626 400 30 "$CAL_OFIR"

    ttbox 18 404 548 400 30 "Jenny" bold

    ttbox 14 476 252 400 30 "$CAL_JENNY"

    # === HOURLY BAR (full width, 7 slots of 100px from x=30) ===
    # Each row is one line, boxed at 3.375*size + 12 for headroom. Slot text
    # is measured, not estimated: "18h" is 43px, "-25°" 59px and "Sunny"
    # 64px against a 100px slot, so nothing wraps into a dropped line.

    _I=0
    while [ $_I -lt 7 ]; do
        _L=$((30 + _I * 100))
        _R=$((628 - _I * 100))
        eval "_T=\$H${_I}T"
        eval "_P=\$H${_I}P"
        eval "_C=\$H${_I}C"
        ttbox 12 774 196 "$_L" "$_R" "$_T"
        ttbox 16 828 130 "$_L" "$_R" "${_P}°" bold
        ttbox 11 894 80 "$_L" "$_R" "$_C"
        _I=$((_I + 1))
    done

    # === FOOTER ===
    # Two clocks on purpose: "Now" proves the script is alive, "Data" is the
    # last successful fetch. When they diverge the weather is stale, which
    # a single redraw-driven timestamp hid completely.
    ttbox 12 960 10 30 30 "Kingston, ON  |  Now ${TIME_NOW}  |  Data ${LAST_FETCH}  |  ebook-dash"

    $FBINK -s -f -W GC16 -q >> "$LOG" 2>&1

    echo "done: $(date)" >> "$LOG"
}

echo "Starting main loop" >> "$LOG"

TEMP="--"; FEELS="--"; HUMID="--"; WINDSP="--"; DESC="No data"
MAXT1="--"; MINT1="--"; MAXT2="--"; MINT2="--"; DAY2=""
CAL_OFIR="Loading..."
CAL_JENNY="Loading..."
LAST_FETCH="--:--"
_LASTBASE=""
reset_hourly
if check_online; then
    fetch_weather
    fetch_calendars
else
    echo "No internet at startup" >> "$LOG"
fi
draw_dashboard

CYCLE=0
while true; do
    sleep 60
    [ -f "$DISABLE" ] && exit 0
    CYCLE=$((CYCLE + 1))
    if [ $((CYCLE % 5)) -eq 0 ]; then
        # ensure_wifi now reports whether the link came back, so a known-down
        # interface skips check_online's 5s probe instead of retrying it.
        if ensure_wifi && check_online; then
            fetch_weather
            fetch_calendars
        else
            echo "Offline, skipping fetch" >> "$LOG"
        fi
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

        for name in ["fbink", "NotoSans-Regular.ttf", "NotoSans-Bold.ttf"]:
            with open(name, "rb") as f:
                data = f.read()
            mode = 0o755 if name == "fbink" else 0o644
            add_bytes(tar, f"usr/local/ebook-dash/{name}", data, mode)
            print(f"  Added {name} ({len(data):,} bytes)")

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
