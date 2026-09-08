"""Print a sanitised, platform-specific inventory of project dependencies."""

import hashlib
import json
import platform
import sys
import tomllib
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def main() -> None:
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    pending = (
        project["project"]["dependencies"]
        + project["project"]["optional-dependencies"]["dev"]
        + project["build-system"]["requires"]
    )
    packages: dict[str, object] = {}
    while pending:
        requirement = Requirement(pending.pop())
        if requirement.marker and not requirement.marker.evaluate():
            continue
        name = canonicalize_name(requirement.name)
        if name in packages:
            continue
        distribution = metadata.distribution(requirement.name)
        notices = []
        for file in distribution.files or []:
            if any(
                word in file.name.lower() for word in ("license", "licence", "copying", "notice")
            ):
                source = distribution.locate_file(file)
                if source.is_file():
                    notices.append(
                        {
                            "file": str(file),
                            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        }
                    )
        packages[name] = {
            "name": name,
            "version": distribution.version,
            "licenseExpression": distribution.metadata.get("License-Expression"),
            "license": distribution.metadata.get("License"),
            "licenseClassifiers": [
                value
                for value in distribution.metadata.get_all("Classifier", [])
                if value.startswith("License")
            ],
            "notices": notices,
            "source": f"https://pypi.org/project/{name}/{distribution.version}/",
        }
        pending.extend(distribution.requires or [])
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": sys.platform,
                "scope": "runtime, development and installed build-tool dependency closure",
                "packages": [packages[key] for key in sorted(packages)],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
