"""Regenerate routing metadata from an explicitly supplied OpenAPI JSON file.

Usage: python tools/update_operations.py /path/to/ifixit-api-v2.json
The input is data only. No schema descriptions or examples are executed.
"""

import hashlib
import json
import pprint
import sys
from pathlib import Path


def generate(source):
    spec = json.loads(Path(source).read_text())
    operations = {}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "head",
                "options",
            }:
                continue
            name = operation["operationId"]
            if name in operations:
                raise ValueError(f"Duplicate operationId: {name}")
            parameters = {(p["in"], p["name"]): p for p in item.get("parameters", [])}
            parameters.update(
                {(p["in"], p["name"]): p for p in operation.get("parameters", [])}
            )
            body = operation.get("requestBody", {})
            content = body.get("content", {})
            content_type = (
                "application/json"
                if "application/json" in content
                else next(iter(content), None)
            )
            schema = content.get(content_type, {}).get("schema", {})
            servers = operation.get("servers", item.get("servers", []))
            operations[name] = {
                "method": method.upper(),
                "path": path,
                "query_required": [
                    p["name"]
                    for p in parameters.values()
                    if p["in"] == "query" and p.get("required")
                ],
                "body_required": body.get("required", False),
                "json_required": (
                    schema.get("required", [])
                    if content_type == "application/json"
                    else []
                ),
                "content_type": content_type,
                "response_types": sorted(
                    {
                        kind
                        for status, response in operation.get("responses", {}).items()
                        if str(status).startswith("2")
                        for kind in response.get("content", {})
                    }
                ),
                "server": servers[0]["url"] if servers else None,
            }
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    output = Path(__file__).resolve().parents[1] / "src/ifixit_client/operations.py"
    header = '''"""Routing from https://www.ifixit.com/api/nextjs/openapi.

Static snapshot, verified 2026-11-09; not a schema validator or live loader.
Regenerate with tools/update_operations.py. See docs/api-compatibility.md.
"""\n\n'''
    output.write_text(
        header
        + f'SOURCE_SHA256 = "{digest}"\n\nOPERATIONS = '
        + pprint.pformat(operations, sort_dicts=False, width=88)
        + "\n"
    )
    print(f"Generated {len(operations)} operations; canonical SHA-256 {digest}")


if __name__ == "__main__":
    generate(sys.argv[1])
