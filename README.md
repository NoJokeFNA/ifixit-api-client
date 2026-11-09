# iFixit API Client

A Python client for the iFixit API v2.0. Requires **Python 3.11 or newer**.

Fetch guides, device wikis, model variants, users, teams and media through
convenience methods or the documented OpenAPI operation names. The client supports
personal API keys, legacy session tokens, optional proxies, custom CA certificates
and SHA-256 certificate pinning.

The [compatibility report](docs/api-compatibility.md) describes the verified
snapshot of 143 operations, known limitations and deprecated methods.

## Installation

Install the stable source from `master`:

```sh
python -m pip install "git+https://github.com/NoJokeFNA/ifixit-api-client.git@master"
```

For development or pre-release changes, use `@develop` instead. To install a local
checkout, run `python -m pip install .` in the repository directory.

There is no production PyPI release yet. A
[TestPyPI candidate](https://test.pypi.org/project/ifixit-api-client/0.1.0rc1/)
is available for evaluation.

## Quick start

Create an iFixit API key as described below and set `IFIXIT_TOKEN` in your
environment. The example reads that variable explicitly; the client itself does
not automatically load environment credentials.

```python
import os

from ifixit_client import IFixitAPIClient

client = IFixitAPIClient(api_key=os.environ["IFIXIT_TOKEN"])
guides = client.get_guides(limit=10, offset=0)
for guide in guides:
    print(guide["title"], guide["url"])
```

The default client ignores environment proxies and verifies TLS certificates.
No proxy, custom CA or certificate pin is needed for ordinary direct access.

### Authentication

For a script or CI job, sign in to iFixit and open
[Profile → API keys](https://www.ifixit.com/User/api_keys). Create a named key,
choose read-only access if you only fetch content, and store it securely.
Keys can last up to one year and are created through the website.
Pass the key with `api_key=...`; the client sends `Authorization: Bearer ...`.

The [official documentation](https://www.ifixit.com/api-docs) announces the end of
anonymous public reads on **January 1, 2027**, with temporary brownouts in
December 2026. Public reads still work anonymously during this transition.

| Credential | Constructor |
|---|---|
| Personal API key | `IFixitAPIClient(api_key=key)` |
| Legacy session token | `IFixitAPIClient(auth_token=token)` |
| OIDC access token | `IFixitAPIClient(auth_token=access_token, auth_scheme="Bearer")` |

Use either `api_key` or `auth_token`, not both. A personal API key and a legacy
session token use different authorization schemes and are not interchangeable.

For an existing password-based integration, `POST /user/token` returns
`authToken`, which is sent using the `api` scheme:

```python
from getpass import getpass

from ifixit_client import IFixitAPIClient

login = IFixitAPIClient(app_id="your_registered_app_id")
result = login.create_user_token({
    "email": input("iFixit email: "),
    "password": getpass("iFixit password: "),
})
client = IFixitAPIClient(auth_token=result["authToken"])
```

Do not print or commit the login response or credentials. Password login may end
older sessions and does not work for accounts that sign in only through an
identity provider. The documentation requires `X-App-Id` for legacy login and
registration when public registration is enabled. Obtain an App ID through the
[iFixit developers page](https://www.ifixit.com/Developers); it is separate from
your user credential.

Approved OIDC integrations obtain an **access token**, not an ID token, through
iFixit's browser sign-in flow. This SDK accepts existing access tokens; it does
not implement OIDC registration, sign-in or refresh. Workbench requires its own
registered resource and `workbench` scope; a personal API key or general `api`
grant does not qualify. FixBot chat requires an active subscription.

A write-capable API key can revoke itself with `delete_user_token()`. Revoke a
read-only key through the website.

### Paginated guide reads

`get_all_guides()` fetches pages and yields parsed `Guide` models:

```python
for guide in client.get_all_guides(page_size=100, limit=250):
    print(guide.title)
```

Use `raw=True` for the original dictionaries or `parser=...` for a custom parser.
The helper handles server page-size caps. Typed models preserve additional API
fields rather than discarding them.

### Calling OpenAPI operations

Use the exact `operationId` from the official OpenAPI download:

```python
wiki = client.call("getWiki", path_params={
    "namespace": "CATEGORY", "title": "Fairphone_5",
})
variants = client.call("listTopicVariants", path_params={"title": "iPhone_13"})
```

`call()` supports all 143 operations in the pinned snapshot. It encodes path
segments and checks required path/query parameters and top-level JSON fields.
It does not validate full nested schemas or credential permissions. Binary
uploads use `body=...`; image uploads require a concrete `content_type` such as
`image/png`. Streaming operations return a `requests.Response`; consume it with
`iter_lines()` and close it when finished.

Guide/wiki update and delete methods, guide steps and guide publication changes
require the current `revisionid`. A conflict
(HTTP 409) requires fetching the current revision and reviewing the edit before
resubmitting it. Deprecated methods retain their existing request behavior and
emit `DeprecationWarning`; see the [migration guidance](docs/api-compatibility.md).

## Proxy settings

**Proxy support is off by default (`proxy=False`).** Environment variables such as
`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and `NO_PROXY` have no effect on the default
client. This also applies to their lowercase forms.

To use the proxy settings already configured in your environment:

```python
client = IFixitAPIClient(
    api_key=os.environ["IFIXIT_TOKEN"],
    proxy=True,
)
```

This enables Requests' environment integration, including `NO_PROXY` exclusions,
environment CA bundles and `.netrc` discovery. HTTPS traffic through a proxy keeps
TLS certificate verification enabled. The proxy option does not configure a proxy
server itself; Requests reads its address from your environment.

## TLS certificates

For ordinary public HTTPS certificates, use the default client. With the default
`proxy=False`, Requests also ignores `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` and
`.netrc`; pass a custom CA explicitly if needed.

### Custom CA bundle

```python
client = IFixitAPIClient(
    api_key=os.environ["IFIXIT_TOKEN"],
    ca_bundle="certs/company-ca.pem",
)
```

`ca_bundle` accepts a PEM CA bundle file or a hashed CA directory. It can be used
with or without a proxy. Supply CA certificates, never a private key.

### Optional certificate pin

```python
client = IFixitAPIClient(
    api_key=os.environ["IFIXIT_TOKEN"],
    certificate_fingerprint=os.environ["IFIXIT_CERT_SHA256"],
)
```

The pin is the SHA-256 fingerprint of the complete DER-encoded leaf server
certificate: 64 hexadecimal digits, optionally colon-separated or prefixed with
`sha256:`. Normal CA-chain and hostname verification must still pass. You can
combine `ca_bundle` and `certificate_fingerprint` when both are needed.

The pin is checked during TLS setup, before API request headers are sent. Pinned
clients reject HTTP, HTTPS-to-HTTP redirects and attempts to disable TLS
verification. Certificate renewal changes the fingerprint; obtain the replacement
through a trusted channel. A configured pin applies to every HTTPS host contacted
by that client, including documented server overrides such as FixBot.

## Configuration and errors

| Option | Default | Purpose |
|---|---|---|
| `api_key` | `None` | Personal API key sent as Bearer |
| `auth_token` | `None` | Legacy session token or OIDC access token |
| `auth_scheme` | `"api"` | Scheme for `auth_token`; use `"Bearer"` for OIDC |
| `app_id` | `None` | Optional `X-App-Id` header |
| `proxy` | `False` | Enable Requests' environment integration |
| `ca_bundle` | `None` | Explicit custom CA bundle or directory |
| `certificate_fingerprint` | `None` | Optional SHA-256 leaf certificate pin |
| `retries` | `3` | Maximum automatic retries for eligible requests |
| `backoff_factor` | `0.5` | Retry backoff multiplier |
| `timeout` | `30` | Requests timeout in seconds |
| `raise_for_status` | `True` | Raise `requests.HTTPError` on HTTP errors |
| `log_level` | `logging.INFO` | Logging level |

HTTP-status retries cover GET, HEAD and OPTIONS on HTTP 429, 500, 502, 503 and 504.
Write requests are not replayed after an HTTP error response or a read failure.
Connection-establishment failures can also be retried before a request is sent.
Other request failures propagate as Requests exceptions. Client request debug
messages omit request bodies and authentication headers.

## Examples and documentation

After installing the client and setting `IFIXIT_TOKEN`, run the read-only example:

```sh
python examples/example_usage.py
```

- [Official iFixit API documentation](https://www.ifixit.com/api-docs)
- [API compatibility and migration guidance](docs/api-compatibility.md)
- [Contributing](CONTRIBUTING.md)
- [Issue tracker](https://github.com/NoJokeFNA/ifixit-api-client/issues)

## License

[MIT](LICENSE).
