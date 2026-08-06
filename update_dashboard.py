"""One-click: fetch weather, generate dashboard, push to Kobo.

Usage: py update_dashboard.py
Requires Kobo to be connected via USB.
"""
import shutil
import sys
import os
import string

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def find_kobo_drive():
    """Find the Kobo's USB drive letter."""
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        kobo_dir = os.path.join(drive, ".kobo")
        if os.path.isdir(kobo_dir):
            version_file = os.path.join(kobo_dir, "version")
            if os.path.isfile(version_file):
                return f"{letter}:"
    return None


def main():
    drive = find_kobo_drive()
    if not drive:
        print("ERROR: Kobo not found. Connect via USB and tap 'Connect'.")
        sys.exit(1)
    print(f"Kobo found at {drive}\\")

    # Generate dashboard
    import dashboard
    dashboard.main()

    # Copy dashboard raw framebuffer data to Kobo
    src = "dashboard.raw"
    dst = os.path.join(drive + "\\", "dashboard.raw")
    shutil.copy2(src, dst)
    print(f"Copied {src} -> {dst}")

    # Check if KoboRoot.tgz needs to be deployed (first run)
    koboroot = os.path.join(drive + "\\", ".kobo", "KoboRoot.tgz")
    marker = os.path.join(drive + "\\", ".kobo", "ebook-dash-installed")
    if not os.path.exists(marker):
        import build_koboroot
        build_koboroot.build_koboroot()
        shutil.copy2("KoboRoot.tgz", koboroot)
        print(f"Deployed KoboRoot.tgz (first install)")
        print("\n*** Safely eject and reboot Kobo to install ***")
        with open(marker, "w") as f:
            f.write("installed")
    else:
        print("\nDashboard updated! Eject Kobo - it will show on next boot.")


if __name__ == "__main__":
    main()
