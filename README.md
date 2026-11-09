# iFixit API Client

A Python client for the iFixit API v2.0.

This README describes `develop` (pre-release). `master` is the stable release
branch; use its README for the stable interface. Feature changes and routine
Dependabot updates target `develop`. Promotion to `master` happens through a
reviewed release PR after CI passes; there is no automatic merge.

This client provides a comprehensive interface to interact with all documented endpoints of the iFixit API, including Guides, Wikis, Users, Teams, Authentication, Media, and more. It features robust error handling, retries with exponential backoff, logging, and support for authentication.

## Features
- Full coverage of iFixit API v2.0 endpoints.
- Authentication support via API tokens.
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

client = IFixitAPIClient(auth_token='your_api_token', app_id='your_app_id')
```

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
on Python 3.9 and 3.13. The tests generate temporary test certificates with
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
Refer to the official iFixit API docs: [https://www.ifixit.com/api/2.0/doc/](https://www.ifixit.com/api/2.0/doc/)

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
