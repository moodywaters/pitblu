from pathlib import Path


def test_optional_systemd_example_is_unprivileged_and_hardened():
    root = Path(__file__).parents[1]
    unit = (root / "deploy" / "pitblu-app.service").read_text()
    assert "User=pitblu-app" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ReadWritePaths=/var/lib/pitblu-app" in unit
    assert "pitblu-core.service" in unit


def test_environment_example_contains_no_secret():
    root = Path(__file__).parents[1]
    environment = (root / "deploy" / "environment.example").read_text()
    assert "PITBLU_CORE_TOKEN=" not in environment
    assert "PITBLU_APP_DATABASE=/var/lib/pitblu-app/state.sqlite3" in environment


def test_frontend_is_built_static_and_production_has_no_node_runtime():
    root = Path(__file__).parents[1]
    package = (root / "frontend" / "package.json").read_text()
    unit = (root / "deploy" / "pitblu-app.service").read_text()
    assert '"build": "tsc --noEmit && vite build"' in package
    assert (root / "src" / "pitblu_app" / "static" / "index.html").is_file()
    assert any((root / "src" / "pitblu_app" / "static" / "assets").glob("index-*.js"))
    assert "node" not in unit.lower()
