"""Compare published TestPyPI file hashes with the tested build artifacts."""

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

version = os.environ["RELEASE_VERSION"]
url = f"https://test.pypi.org/pypi/ifixit-api-client/{version}/json"
expected = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in Path("dist").iterdir()
    if path.is_file()
}
for attempt in range(12):
    try:
        with urlopen(url, timeout=30) as response:
            payload = json.load(response)
        actual = {
            entry["filename"]: entry["digests"]["sha256"] for entry in payload["urls"]
        }
        if actual == expected:
            break
        print("Waiting for both published files to appear with the expected hashes")
    except HTTPError as exc:
        if exc.code != 404:
            raise
        print("Waiting for the new TestPyPI version to appear")
    time.sleep(10)
else:
    raise RuntimeError("Published distribution hashes do not match the tested build")
print(f"Verified both TestPyPI distribution hashes for {version}")
with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as summary:
    summary.write(
        f"Published [{version}](https://test.pypi.org/project/ifixit-api-client/{version}/) "
        "and verified both distribution hashes.\n"
    )
