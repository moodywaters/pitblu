"""Catch broken local links when current documentation is reorganised."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def test_documentation_local_file_links_exist() -> None:
    root = Path(__file__).parents[1]
    documents = [*root.glob("*.md"), *(root / "docs").rglob("*.md")]
    for document in documents:
        content = document.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            target = target.strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith(("#", "//")):
                continue
            path = unquote(parsed.path)
            if not path:
                continue
            assert (document.parent / path).exists(), f"{document.name}: {target}"
