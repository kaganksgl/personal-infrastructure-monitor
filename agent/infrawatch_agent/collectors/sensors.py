"""Temperatures from the hwmon subsystem, falling back to thermal zones.

/sys/class/hwmon/hwmonN/ holds one directory per hardware monitoring chip
(``name`` = driver, e.g. coretemp, k10temp, amdgpu, nvme). Each sensor is a
``tempK_input`` file in millidegrees Celsius, optionally with ``_label``,
``_max`` and ``_crit`` siblings. Many machines (VMs, containers, some ARM
boards) expose nothing at all: that yields an empty list, never an error.
"""

from pathlib import Path
from typing import Any

from infrawatch_agent.collectors.base import HostPaths, read_int, read_text

_CHIP_KINDS = {
    "coretemp": "cpu",
    "k10temp": "cpu",
    "zenpower": "cpu",
    "cpu_thermal": "cpu",
    "soc_thermal": "cpu",
    "amdgpu": "gpu",
    "radeon": "gpu",
    "nouveau": "gpu",
    "i915": "gpu",
    "xe": "gpu",
    "nvme": "nvme",
    "drivetemp": "disk",
    "iwlwifi_1": "wifi",
    "acpitz": "acpi",
}
_PLAUSIBLE_C = (-40.0, 150.0)


def classify(chip: str) -> str:
    if chip in _CHIP_KINDS:
        return _CHIP_KINDS[chip]
    if chip.startswith("iwlwifi"):
        return "wifi"
    if "cpu" in chip or chip.startswith("x86_pkg"):
        return "cpu"
    if "gpu" in chip:
        return "gpu"
    return "other"


def _millidegrees(path: Path) -> float | None:
    value = read_int(path)
    if value is None:
        return None
    celsius = value / 1000
    return round(celsius, 1) if _PLAUSIBLE_C[0] <= celsius <= _PLAUSIBLE_C[1] else None


class SensorCollector:
    name = "sensors"

    def __init__(self, paths: HostPaths) -> None:
        self._paths = paths

    def prime(self) -> None:
        pass

    def collect(self) -> dict[str, Any]:
        temps = self._hwmon() or self._thermal_zones()
        return {"temperatures": temps[:128]}

    def _hwmon(self) -> list[dict[str, Any]]:
        root = self._paths.sys / "class" / "hwmon"
        sensors: list[dict[str, Any]] = []
        try:
            chips = sorted(root.iterdir())
        except OSError:
            return sensors
        for chip_dir in chips:
            chip = read_text(chip_dir / "name", chip_dir.name) or chip_dir.name
            for input_file in sorted(chip_dir.glob("temp*_input")):
                current = _millidegrees(input_file)
                if current is None:
                    continue
                stem = input_file.name.removesuffix("_input")
                label = read_text(chip_dir / f"{stem}_label") or stem
                sensors.append(
                    {
                        "chip": chip[:64],
                        "label": label[:64],
                        "kind": classify(chip),
                        "current_c": current,
                        "high_c": _millidegrees(chip_dir / f"{stem}_max"),
                        "critical_c": _millidegrees(chip_dir / f"{stem}_crit"),
                    }
                )
        return sensors

    def _thermal_zones(self) -> list[dict[str, Any]]:
        root = self._paths.sys / "class" / "thermal"
        sensors: list[dict[str, Any]] = []
        try:
            zones = sorted(root.glob("thermal_zone*"))
        except OSError:
            return sensors
        for zone in zones:
            current = _millidegrees(zone / "temp")
            if current is None:
                continue
            zone_type = read_text(zone / "type", zone.name) or zone.name
            sensors.append(
                {
                    "chip": zone_type[:64],
                    "label": zone.name,
                    "kind": classify(zone_type),
                    "current_c": current,
                }
            )
        return sensors
