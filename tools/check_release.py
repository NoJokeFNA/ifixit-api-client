"""Validate a manual TestPyPI release and its built distribution metadata."""

import argparse
import os
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from packaging.utils import canonicalize_name, parse_sdist_filename
from packaging.version import InvalidVersion, Version


def validate_version(value):
    try:
        parsed = Version(value)
    except InvalidVersion as exc:
        raise ValueError("Use a PEP 440 version, e.g. 0.1.0rc1") from exc
    if str(parsed) != value or parsed.local is not None:
        raise ValueError("Use a canonical public version without a local (+) suffix")
    return parsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path)
    args = parser.parse_args()
    version = validate_version(os.environ["RELEASE_VERSION"])
    if os.environ.get("GITHUB_REF", "refs/heads/master") != "refs/heads/master":
        raise ValueError("Test releases must be built from master")
    if args.dist:
        files = list(args.dist.iterdir())
        wheels = [p for p in files if p.suffix == ".whl"]
        sources = [p for p in files if p.name.endswith(".tar.gz")]
        if len(files) != 2 or len(wheels) != 1 or len(sources) != 1:
            raise ValueError("Expected exactly one wheel and one source distribution")
        with ZipFile(wheels[0]) as wheel:
            metadata_files = [
                n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")
            ]
            if len(metadata_files) != 1:
                raise ValueError("Expected exactly one wheel metadata file")
            metadata = BytesParser().parsebytes(wheel.read(metadata_files[0]))
        if canonicalize_name(metadata["Name"]) != "ifixit-api-client":
            raise ValueError("Unexpected wheel package name")
        if Version(metadata["Version"]) != version:
            raise ValueError("Wheel version does not match requested release")
        source_name, source_version = parse_sdist_filename(sources[0].name)
        if source_name != "ifixit-api-client" or source_version != version:
            raise ValueError("Source distribution does not match requested release")
    print(f"Validated ifixit-api-client {version} from master")


if __name__ == "__main__":
    main()
