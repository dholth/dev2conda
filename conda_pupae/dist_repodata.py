"""
Convert Python *.dist-info/METADATA to conda info/index.json
"""

import logging
import sys
from importlib.metadata import Distribution, PathDistribution
from pathlib import Path
from typing import Any

from conda.exceptions import InvalidMatchSpec
from conda.models.match_spec import MatchSpec
from packaging.requirements import Requirement

log = logging.getLogger(__name__)


def pypi_to_conda(requirement):
    # minimal for testing against this project; see grayskull, conda-pypi, ...
    mapping = {"build": "python-build"}
    requirement.name = mapping.get(requirement.name, requirement.name)
    return requirement


class FileDistribution(Distribution):
    """
    From a file e.g. a single .metadata fetched from pypi instead of a
    *.dist-info folder.
    """

    def __init__(self, raw_text):
        self.raw_text = raw_text

    def read_text(self, filename: str) -> str | None:
        if filename == "METADATA":
            return self.raw_text
        else:
            return None


def fetch_data(metadata_path):
    recipe: dict[str, Any] = {"requirements": {}, "build": {}}

    distribution = PathDistribution(metadata_path)
    metadata = distribution.metadata.json

    requires_python = metadata.get("requires_python")
    if requires_python:
        requires_python = f"python { requires_python }"
    else:
        requires_python = "python"

    requirements = [pypi_to_conda(Requirement(r)) for r in distribution.requires or []]
    active_requirements = [
        str(r).rsplit(";", 1)[0]
        for r in requirements
        if not r.marker or r.marker.evaluate()
    ]
    # XXX to normalize space between name and version, MatchSpec(r).spec
    normalized_requirements = []
    for requirement in active_requirements:
        try:
            normalized_requirements.append(
                # MatchSpec uses a metaclass hiding its constructor from
                # the type checker
                MatchSpec(requirement).spec  # type: ignore
            )
        except InvalidMatchSpec:
            log.warning("%s is not a valid MatchSpec", requirement)
            normalized_requirements.append(requirement)

    # conda does support ~=3.0.0 "compatibility release" matches
    recipe["requirements"]["run"] = [requires_python] + normalized_requirements
    # includes extras as markers e.g. ; extra == 'testing'. Evaluate
    # using Marker().

    recipe["build"]["entry_points"] = [
        f"{ep.name} = {ep.value}"
        for ep in distribution.entry_points
        if ep.group == "console_scripts"
    ]

    recipe["build"]["noarch"] = "python"
    recipe["build"]["script"] = (
        "{{ PYTHON }} -m pip install . -vv --no-deps --no-build-isolation"
    )
    # XXX also --no-index?

    # distribution.metadata.keys() for grayskull is
    # Metadata-Version
    # Name
    # Version
    # Summary
    # Author-email
    # License
    # Project-URL
    # Keywords
    # Requires-Python
    # Description-Content-Type
    # License-File
    # License-File
    # Requires-Dist (many times)
    # Provides-Extra (several times)
    # Description or distribution.metadata.get_payload()

    about = {
        "summary": metadata.get("summary"),
        "license": metadata.get("license"),
        # there are two license-file in grayskull e.g.
        "license_file": metadata.get("license_file"),
    }
    recipe["about"] = about

    # XXX
    metadata["entry_points"] = [
        f"{ep.name} = {ep.value}"
        for ep in distribution.entry_points
        if ep.group == "console_scripts"
    ]

    recipe["name"] = distribution.name
    recipe["version"] = distribution.version
    recipe["metadata"] = metadata

    return recipe


if __name__ == "__main__":  # pragma: no cover
    base = sys.argv[1]
    for path in Path(base).glob("*.dist-info"):
        fetch_data(path)