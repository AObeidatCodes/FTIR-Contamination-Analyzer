"""
Builds the Windows app: a folder that runs without Python, zipped to send to someone.

    python -m pip install -r requirements.txt pyinstaller
    python tools/build_windows.py

The result is in dist/: the folder "FTIR Contamination Analyzer" and FTIR-Contamination-Analyzer-<version>-windows.zip.

The program's .py files are copied in beside the compiled ones, so that a report's code checksum is the same as from the
source folder. The Qt libraries stay separate files, so a user can replace them, as the LGPL asks.

Short names used in this file:
    app = the folder of the built app

Author : Ali Obeidat
Version: 2.0.0
License: MIT (see LICENSE)
"""

import importlib.metadata
import re
import shutil
import sys
import tempfile
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ftir_analyzer import __title__, __version__  # noqa: E402

DIST = ROOT / "dist"
APP = DIST / __title__
ZIP_NAME = f"{__title__.replace(' ', '-')}-{__version__}-windows"
SEPARATOR = ";"
LEFT_OUT = ("tkinter", "IPython", "jupyter_client", "jupyter_core", "ipykernel", "notebook", "pytest", "sphinx", "torch",
            "tensorflow", "sklearn", "cv2", "sympy", "dask", "numba", "PyQt5", "PyQt6", "PySide2", "wx")
PACKAGES = ("PySide6-Essentials", "numpy", "pandas", "scipy", "matplotlib", "plotly", "nbformat", "rdata", "openpyxl", "jcamp",
            "brukeropus", "pyinstaller")
LICENCE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE)", re.I)


def demo_files(stage):
    """A copy of the demo files only: a report left in examples/ must not be sent to anyone."""
    target = stage / "examples"
    for folder, pattern in ((".", "*.csv"), (".", "*.md"), ("library_demo", "*"), ("trends_demo", "*.csv")):
        (target / folder).mkdir(parents=True, exist_ok=True)
        for path in (ROOT / "examples" / folder).glob(pattern):
            if path.is_file():
                shutil.copy2(path, target / folder / path.name)
    return target


def needed(name, seen):
    """The name of a package and of everything it needs, each once."""
    key = re.sub(r"[-_.]+", "-", name).lower()
    if key in seen:
        return
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return
    seen[key] = distribution
    for line in distribution.requires or ():
        if "extra ==" not in line:
            needed(re.match(r"[A-Za-z0-9._-]+", line).group(), seen)


def copy_licences(app):
    """The licence file of every package in the app, and the LGPL and GPL texts."""
    target = app / "licenses"
    target.mkdir(exist_ok=True)
    for path in (ROOT / "tools" / "licenses").glob("*.txt"):
        shutil.copy2(path, target / path.name)
    seen = {}
    for name in PACKAGES:
        needed(name, seen)
    for key, distribution in sorted(seen.items()):
        for file in distribution.files or ():
            parts = file.parts
            if ".dist-info" in parts[0] and LICENCE_FILE.search(file.name):
                folder = target / f"{key}-{distribution.version}"
                folder.mkdir(exist_ok=True)
                shutil.copy2(file.locate(), folder / file.name)
    python = Path(sys.base_prefix) / "LICENSE.txt"
    if python.exists():
        shutil.copy2(python, target / "python.txt")
    return len(seen)


def main():
    if sys.platform != "win32":
        raise SystemExit("This builds the Windows app, so it must run on Windows.")
    shutil.rmtree(APP, ignore_errors=True)
    with tempfile.TemporaryDirectory() as folder:
        stage = Path(folder)
        code = stage / "code"
        code.mkdir()
        for path in (ROOT / "ftir_analyzer").glob("*.py"):
            shutil.copy2(path, code / path.name)
        data = [(ROOT / "ftir_analyzer" / "data", "ftir_analyzer/data"), (ROOT / "ftir_analyzer" / "assets", "ftir_analyzer/assets"),
                (code, "ftir_analyzer"), (demo_files(stage), "ftir_analyzer/examples")]
        arguments = [str(ROOT / "run_analyzer.py"), "--noconfirm", "--clean", "--windowed", "--onedir", "--name", __title__,
                     "--icon", str(ROOT / "ftir_analyzer" / "assets" / "logo.ico"), "--distpath", str(DIST),
                     "--workpath", str(ROOT / "build" / "windows"), "--specpath", str(ROOT / "build"),
                     "--paths", str(ROOT), "--collect-data", "plotly", "--collect-data", "nbformat",
                     "--copy-metadata", "xarray", "--copy-metadata", "pandas", "--copy-metadata", "numpy"]
        for source, place in data:
            arguments += ["--add-data", f"{source}{SEPARATOR}{place}"]
        for name in LEFT_OUT:
            arguments += ["--exclude-module", name]
        PyInstaller.__main__.run(arguments)
    packages = copy_licences(APP)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md", "docs/QUICK_START.md"):
        shutil.copy2(ROOT / name, APP / Path(name).name)
    archive = shutil.make_archive(str(DIST / ZIP_NAME), "zip", DIST, APP.name)
    size = sum(path.stat().st_size for path in APP.rglob("*") if path.is_file())
    print(f"{packages} packages' licences copied")
    print(f"{APP}: {size / 1e6:.0f} MB")
    print(f"{archive}: {Path(archive).stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
