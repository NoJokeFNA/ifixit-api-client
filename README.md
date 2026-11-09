# iFixit API Client

A Python client for the iFixit API v2.0.

Requires Python 3.11 or newer.

This README describes `develop` (pre-release). `master` is the stable release
branch; use its README for the stable interface. Feature changes and routine
Dependabot updates target `develop`. Promotion to `master` happens through a
reviewed release PR after CI passes; there is no automatic merge.

This client provides convenience methods for Guides, Wikis, Users, Teams and Media, plus OpenAPI operation routing for the current API snapshot. It features robust error handling, retries with exponential backoff, logging, and support for authentication.

## Features
- Convenience methods plus `call()` routing for all 143 operations in the verified OpenAPI snapshot.
- See [API compatibility, legacy deprecations and migration guidance](docs/api-compatibility.md).
- Personal API keys (Bearer), legacy session tokens, and OIDC access tokens.
- Automatic retries for transient errors (e.g., rate limits, server issues).
- Detailed logging for debugging.
- Type hints for better IDE integration.
- Open-source under the MIT License.

## Installation

You can install the package via pip (if published to PyPI) or directly from GitHub.

### From GitHub
```bash
pip install git+https://github.com/NoJokeFNA/ifixit-api-client.git@develop
```

### Locally
Clone the repository and install:
```bash
git clone https://github.com/NoJokeFNA/ifixit-api-client.git
cd ifixit-api-client
pip install .
```

## Usage

Initialize the client with your API token (required for authenticated endpoints):

```python
from ifixit_client import IFixitAPIClient

import os

client = IFixitAPIClient(api_key=os.environ["IFIXIT_TOKEN"])
```

### Where to get your token

For a script or CI job, sign in to iFixit and open
[Profile → API keys](https://www.ifixit.com/User/api_keys). Create a named key,
choose read-only access if you only fetch content, and store it in your environment
as `IFIXIT_TOKEN`. API keys can last up to one year and are created in the website,
not over the API. Pass the key with `api_key=...`; the SDK sends **Bearer**.
The SDK does not load environment credentials implicitly.

The [official documentation](https://www.ifixit.com/api-docs) announces that
anonymous public reads will end on **January 1, 2027**, with temporary brownouts
in December 2026. Public reads still work anonymously during the transition.

An older `auth_token` is a different credential: `POST /user/token` returns
`authToken` after password login. The existing constructor keeps sending it as
`Authorization: api ...` for compatibility. To obtain one without hardcoding your
password:

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

Do not print or commit the response/token. Password login may end older sessions
and does not work for an account that only signs in through an identity provider;
use a personal API key for new scripts. The documentation requires `X-App-Id`
for legacy login and registration when public registration is enabled. Obtain an
App ID from iFixit through its [developers page](https://www.ifixit.com/Developers);
an App ID is separate from your user credential.

An approved OIDC integration obtains an **access token** through iFixit's browser
sign-in flow and uses `IFixitAPIClient(auth_token=access_token, auth_scheme="Bearer")`.
An ID token is not an API credential. This SDK accepts existing access tokens;
it does not implement registration, browser sign-in, PKCE or token refresh.
Workbench requires its own registered resource and `workbench` scope; a personal
API key or general `api` grant does not qualify. FixBot chat requires an active
subscription. A write-capable API key can revoke itself via `delete_user_token()`;
a read-only key must be revoked through the website.

### Calling newer API operations

Use the exact `operationId` from the official OpenAPI download:

```python
wiki = client.call("getWiki", path_params={
    "namespace": "CATEGORY", "title": "Fairphone_5",
})
```

`call()` validates required path/query parameters and top-level required JSON
fields, encodes path segments, supports binary bodies through `body=...` (set a concrete `content_type` for
`image/*` uploads), and
uses documented server overrides. It does not perform full schema validation or
make every operation available to every credential. Streaming operations return
a `requests.Response`; consume it with `iter_lines()` and close it when finished.
The manifest is pinned in the package, not fetched or executed at runtime.

### Fetching Guides
```python
guides = client.get_guides(limit=10, offset=0)
print(guides)
```

### Creating a Comment
```python
comment_data = {'text': 'Great guide!'}
comment = client.create_comment(context='guide', contextid=1234, data=comment_data)
print(comment)
```

For more examples, see the [examples/](examples/) directory.

## Examples

The `examples/` directory contains sample scripts demonstrating common use cases.

- `example_usage.py`: Basic operations like fetching guides, users, and creating comments.

Run an example:
```bash
python examples/example_usage.py
```

## Configuration Options
- `api_key`: Personal API key sent as Bearer.
- `auth_token`: Legacy session token (`api`), or access token with `auth_scheme="Bearer"`.
- `retries`: Number of retry attempts (default: 3).
- `backoff_factor`: Exponential backoff multiplier (default: 0.5).
- `timeout`: Request timeout in seconds (default: 30).
- `log_level`: Logging level (e.g., `logging.DEBUG`).

## TLS certificates and proxy settings

TLS certificate verification is enabled by default, independently of proxy use.
Environment proxies are ignored unless explicitly enabled with `proxy=True`.
That opt-in honors Requests' proxy environment settings, including `NO_PROXY`.

```python
import os
from ifixit_client import IFixitAPIClient

client = IFixitAPIClient(
    ca_bundle="certs/company-ca.pem",  # Optional custom PEM CA bundle or CA directory.
    certificate_fingerprint=os.environ["IFIXIT_CERT_SHA256"],  # Optional server pin.
    proxy=False,  # Default; set True to opt into environment proxy settings.
)
```

`ca_bundle` and `certificate_fingerprint` can be used separately or together.
Omit `ca_bundle` for normal trusted public certificates. With a private CA,
supply its certificate or CA bundle; never supply a private key.

The pin is the **SHA-256 fingerprint of the complete DER-encoded leaf server
certificate**. It accepts 64 hexadecimal digits or colon-separated hexadecimal
bytes, optionally prefixed with `sha256:`. It is checked during connection setup,
after CA/hostname validation and before API HTTP headers or API authentication are sent.
A pin does not replace certificate-chain or hostname verification. Pinned clients
reject HTTP, HTTPS-to-HTTP redirects, and attempts to disable TLS verification.
Certificate renewal changes the leaf fingerprint: obtain the new fingerprint via
a trusted channel and create a new client with the updated pin.

Read requests (GET, HEAD, OPTIONS) retry transient failures. Mutating requests
are not automatically repeated. `get_all_guides` streams results and supports
`limit`, `raw=True`, and custom parsers; it also handles server page-size caps.

## Development checks

CI builds and installs a wheel, then runs unit and local HTTPS integration tests
on Python 3.11 and 3.13. The tests generate temporary test certificates with
OpenSSL; no production API calls, tokens, or private certificates are required.

```sh
python -m pip install build
python -m build
python -m pip install dist/*.whl
python -m unittest discover -s tests -v
```

Dependabot checks Python dependencies and Actions weekly, opening PRs against
`develop`. Its configuration also lives on the default `master` branch so GitHub
can discover it. Stable security fixes can be handled as reviewed hotfixes.

## API Documentation
Refer to the official iFixit API docs: [https://www.ifixit.com/api-docs](https://www.ifixit.com/api-docs)

Note: Always respect iFixit API rate limits and terms of service.

## Contributing
Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a feature branch from `develop` (`git switch -c feature/YourFeature develop`).
3. Commit your changes (`git commit -m 'Add YourFeature'`).
4. Push to the branch (`git push origin feature/YourFeature`).
5. Open a Pull Request.

We adhere to the Google Python Style Guide. Run `black` or `yapf` for formatting.

## License
MIT License - see [LICENSE](LICENSE) for details.

## Support
For issues, open a GitHub Issue. For questions, contact via GitHub Discussions.

## TestPyPI releases

The manually started **Publish to TestPyPI** workflow is
[`.github/workflows/publish-testpypi.yml`](.github/workflows/publish-testpypi.yml).
It publishes only to TestPyPI, never to production PyPI. Keep the TestPyPI token
in the repository Actions secret `TEST_PYPI_API_TOKEN`; do not commit it.

1. Merge reviewed code into `master` after normal CI passes.
2. In GitHub Actions, choose **Publish to TestPyPI → Run workflow**, select
   **master**, and enter a new canonical PEP 440 version, e.g. `0.1.0rc1`.
3. The workflow builds a wheel and source distribution once, checks their metadata
   and versions, and runs the installed-wheel tests on Python 3.11 and 3.13.
4. Only those tested files are uploaded. The final job compares TestPyPI's file
   hashes, installs the exact version from TestPyPI, and repeats the package tests.

Uploads create the TestPyPI project on the first successful publication. Versions
cannot be overwritten or reused: use `0.1.0rc2` for a changed candidate. If an upload
partially succeeds, inspect its files before choosing a recovery; the workflow does
not silently skip existing files. A verification failure after upload does not undo
the publication. `setuptools-scm` receives the requested version only for this build;
this does not create a stable Git tag or publish a GitHub/PyPI production release.

For a local installation of a published test candidate, fetch its dependencies
from regular PyPI first, then install only the client from TestPyPI:

```sh
python -m pip install 'requests' 'urllib3' 'pydantic>=2,<3' 'typing_extensions>=4.9'
python -m pip install --no-deps --only-binary=:all: \
  --index-url https://test.pypi.org/simple/ ifixit-api-client==0.1.0rc1
```

Avoid mixing TestPyPI and production PyPI using `--extra-index-url`. TestPyPI is a
staging service; the production website will keep its current dependency setup
until the client has a verified production PyPI release. A production publisher
with OIDC Trusted Publishing will be configured separately when the PyPI account
is ready. TestPyPI and PyPI credentials are not interchangeable.
