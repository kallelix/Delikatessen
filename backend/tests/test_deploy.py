"""Deploy-Skripte: install.sh verweist nur auf Units, die es auch gibt."""

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def _installed_units() -> list[str]:
    text = (DEPLOY / "install.sh").read_text(encoding="utf-8").replace("\\\n", " ")
    units = re.findall(r"deploy/systemd/([\w.-]+)\"", text)
    for loop in re.findall(r"^for unit in (.+?); do$", text, re.M):
        units += loop.split()
    return units


def test_install_units_exist():
    units = _installed_units()
    assert units
    missing = [u for u in units if not (DEPLOY / "systemd" / u).is_file()]
    assert missing == []


def test_every_unit_is_installed():
    units = set(_installed_units())
    files = {p.name for p in (DEPLOY / "systemd").iterdir()}
    assert files - units == set()
