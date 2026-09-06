#!/usr/bin/env python3

import os
import sys
import tomllib
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
with open(project_root / "pyproject.toml", "rb") as pyproject_file:
    version = tomllib.load(pyproject_file)["project"]["version"].strip()

resource_attributes = [
    attribute.strip()
    for attribute in os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "").split(",")
    if attribute.strip()
]
if not any(attribute.startswith("service.version=") for attribute in resource_attributes):
    resource_attributes.append(f"service.version={version}")

os.environ["VERSION"] = version
os.environ["OTEL_RESOURCE_ATTRIBUTES"] = ",".join(resource_attributes)
os.chdir(project_root)
os.execvp(
    "opentelemetry-instrument",
    ["opentelemetry-instrument", sys.executable, "src/main.py"],
)
