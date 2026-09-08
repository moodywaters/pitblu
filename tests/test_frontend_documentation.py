"""Keep the frontend handoff's inventories aligned with the public surface."""

import re
from pathlib import Path

from fastapi.routing import APIRoute

from pitboss_admin.api import create_app
from pitboss_admin.configuration import ConfigurationManager
from pitboss_admin.events import EventType
from pitboss_admin.storage import AdministrativeStore


def test_frontend_guide_covers_routes_settings_and_events() -> None:
    guide = (Path(__file__).parents[1] / "docs" / "frontend-integration.md").read_text(
        encoding="utf-8"
    )
    normalised = re.sub(r"\{[^{}\n]+\}", "{parameter}", guide)
    store = AdministrativeStore()
    try:
        configuration = ConfigurationManager(store, environ={})
        app = create_app(store=store, configuration=configuration)
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            paths = (
                [
                    route.path.replace("{action}", action)
                    for action in ("connect", "disconnect", "reconnect")
                ]
                if "{action}" in route.path
                else [route.path]
            )
            for path in paths:
                # The sole secret route exposes mqtt.password, not arbitrary names.
                path = path.replace("{secret_name}", "mqtt.password")
                path = re.sub(r"\{[^{}]+\}", "{parameter}", path)
                for method in route.methods or set():
                    assert f"`{method} {path}`" in normalised
        for setting in configuration.describe()["settings"]:
            assert f"`{setting}`" in guide
        for event_type in EventType:
            assert f"`{event_type.value}`" in guide
    finally:
        store.close()
