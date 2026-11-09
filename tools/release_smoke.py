"""Check the installed distribution, without sending API requests."""

import os
from importlib.metadata import version
from pathlib import Path

import ifixit_client
from ifixit_client import IFixitAPIClient
from ifixit_client.operations import OPERATIONS

expected = os.environ["RELEASE_VERSION"]
assert version("ifixit-api-client") == expected
assert ifixit_client.__version__ == expected
source = Path(__file__).resolve().parents[1] / "src"
assert not Path(ifixit_client.__file__).resolve().is_relative_to(source)
with_key = IFixitAPIClient(api_key="release-smoke-placeholder")
assert with_key._build_headers()["Authorization"] == "Bearer release-smoke-placeholder"
assert "getWiki" in OPERATIONS and "listTopicVariants" in OPERATIONS
print(f"Installed ifixit-api-client {expected}: imports and API smoke checks passed")
