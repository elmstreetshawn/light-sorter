#!/usr/bin/env python3
"""
Light Sorter — a one-click Mac app.

Double-click: asks for a folder, then sorts the images in it (and in every
folder inside it) from lightest to darkest.
Or drag folders onto the app icon.

Each folder gets a "sorted_light_to_dark" subfolder with numbered copies.
Original files are never moved, renamed or changed.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageStat

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC = {".heic", ".heif"}
except Exception:
    HEIC = set()

APP = "Light Sorter"
OUT_NAME = "sorted_light_to_dark"
EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"} | HEIC


# ---------- macOS dialogs (AppleScript, no extra libraries needed) ----------

def osa(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def choose_folder() -> Path | None:
    p = osa(
        f'POSIX path of (choose folder with prompt '
        f'"Pick the folder that holds your image folders (or one folder of images):")'
    )
    return Path(p) if p else None


def notify(msg: str) -> None:
    osa(f'display notification "{esc(msg)}" with title "{APP}"')


def message(msg: str, buttons=("OK",), icon="note") -> str:
    btns = ", ".join(f'"{esc(b)}"' for b in buttons)
    out = osa(
        f'display dialog "{esc(msg)}" with title "{APP}" buttons {{{btns}}} '
        f'default button "{esc(buttons[-1])}" with icon {icon}'
    )
    return out.split("button returned:")[-1] if out else ""


# ---------- the actual work ----------

def brightness(path: Path) -> float:
    """Average perceived brightness, 0 (black) to 255 (white)."""
    with Image.open(path) as im:
        im.thumbnail((400, 400))
        if im.mode in ("RGBA", "LA", "P") and (
            im.mode != "P" or "transparency" in im.info
        ):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im)
        return ImageStat.Stat(im.convert("L")).mean[0]


def sort_folder(folder: Path, problems: list) -> int:
    images = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith(".")
    )
    if not images:
        return 0

    scored = []
    for p in images:
        try:
            scored.append((brightness(p), p))
        except Exception:
            problems.append(f"{folder.name}/{p.name}")

    scored.sort(key=lambda t: t[0], reverse=True)  # lightest first

    out = folder / OUT_NAME
    if out.exists():
        shutil.rmtree(out)  # only ever the app's own output folder
    out.mkdir()

    width = max(3, len(str(len(scored))))
    for i, (_, p) in enumerate(scored, 1):
        shutil.copy2(p, out / f"{i:0{width}d}_{p.name}")
    return len(scored)


def run(roots: list[Path]) -> None:
    targets = []
    for root in roots:
        if root.is_dir():
            targets.append(root)
            targets += sorted(
                d for d in root.iterdir()
                if d.is_dir() and d.name != OUT_NAME and not d.name.startswith(".")
            )

    notify("Sorting images… this can take a minute.")

    problems, done_folders, total = [], [], 0
    for d in targets:
        n = sort_folder(d, problems)
        if n:
            done_folders.append(d)
            total += n

    if not done_folders:
        message("No images were found in that folder.", icon="caution")
        return

    msg = (
        f"Done! Sorted {total} images in {len(done_folders)} "
        f"folder{'s' if len(done_folders) != 1 else ''}.\n\n"
        f"Look inside each folder for “{OUT_NAME}”. "
        f"File 001 is the lightest. Your original files were not changed."
    )
    if problems:
        msg += f"\n\n{len(problems)} file(s) couldn't be read and were left out."
    if message(msg, buttons=("Close", "Show in Finder")) == "Show in Finder":
        subprocess.run(["open", str(done_folders[0] / OUT_NAME)])


def main():
    dropped = [Path(a) for a in sys.argv[1:] if not a.startswith("-psn")]
    roots = [p for p in dropped if p.is_dir()]
    if not roots:
        folder = choose_folder()
        if not folder:
            return
        roots = [folder]
    try:
        run(roots)
    except Exception as e:
        message(f"Something went wrong:\n\n{e}", icon="stop")


if __name__ == "__main__":
    main()
