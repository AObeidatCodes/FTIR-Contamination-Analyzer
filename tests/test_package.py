"""The release files agree with each other, and an installed copy has what the source folder has."""
import re
from pathlib import Path

from ftir_analyzer import __version__, config

ROOT = Path(__file__).resolve().parent.parent


def text(name):
    return (ROOT / name).read_text(encoding="utf-8")


def names(lines):
    """The package names in lines such as 'numpy>=1.24'."""
    return {re.split(r"[<>=\s]", line.strip().strip('",'))[0].casefold() for line in lines}


def test_every_version_is_the_same():
    assert f'version = "{__version__}"' in text("pyproject.toml")
    assert f"version: {__version__}" in text("CITATION.cff")
    assert f"version {__version__}" in text("README.md")
    assert f"## {__version__}" in text("CHANGELOG.md")


def test_an_installed_package_needs_what_the_source_folder_needs():
    required = [line for line in text("requirements.txt").splitlines() if line and not line.startswith("#")]
    block = re.search(r"dependencies = \[(.*?)\]", text("pyproject.toml"), re.S).group(1)
    assert names(required) == names(line for line in block.splitlines() if line.strip())


def test_the_demo_files_are_packaged():
    project = text("pyproject.toml")
    for folder in ("ftir_analyzer.examples", "ftir_analyzer.examples.library_demo", "ftir_analyzer.examples.trends_demo"):
        assert f'"{folder}"' in project
    assert (ROOT / "examples" / "library_demo").is_dir() and config.TRENDS_DEMO_DIR.is_dir()


def test_the_documents_name_no_old_badge():
    for name in ("README.md", "docs/QUICK_START.md", "examples/CHECK_IT_YOURSELF.md"):
        assert "Library validated" not in text(name) and "probably no sample" not in text(name)
