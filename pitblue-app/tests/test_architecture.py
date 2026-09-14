import ast
from pathlib import Path

from pitblue_app.store import SCHEMA

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "pitblue_app"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_application_has_no_host_or_hardware_dependencies():
    forbidden = ("RPi", "gpio", "bluez", "bleak", "dbus", "pitblu_core")
    modules = {module for path in SOURCE.rglob("*.py") for module in imported_modules(path)}
    assert not {
        module
        for module in modules
        if module.lower().startswith(tuple(value.lower() for value in forbidden))
    }
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert not any(name in project for name in ("rpi.gpio", "gpiozero", "bleak", "bluez"))


def test_schema_uses_collections_and_composite_physical_identity():
    schema = SCHEMA.lower()
    assert "cook.igrill_id" not in schema
    assert "igrill_id" not in schema
    assert all(f"probe_{number}" not in schema for number in range(1, 5))
    assert "core_device_id" in schema and "probe_channel" in schema
    assert "active_source_assignment" in schema
    assert "assignments(core_device_id, probe_channel)" in schema


def test_cook_domain_does_not_depend_on_gateway_client():
    service_imports = imported_modules(SOURCE / "service.py")
    model_imports = imported_modules(SOURCE / "models.py")
    assert "pitblue_app.core_client" not in service_imports | model_imports
    adapter = (SOURCE / "core_client.py").read_text(encoding="utf-8")
    assert "class PitbluCoreClient" in adapter
    assert "class ThermometerGateway" in adapter
    assert "Blower" not in adapter
