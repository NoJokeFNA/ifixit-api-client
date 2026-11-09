# Contributing

Use Python 3.11 or newer. Start feature branches from `develop` and open a pull
request against `develop`. `master` contains stable code; promote reviewed changes
after CI passes. Routine Dependabot updates target `develop`; stable security fixes
can be handled as reviewed hotfixes.

## Local checks

Build and install a wheel, then run the tests:

```sh
python -m pip install build
python -m build
python -m pip install dist/*.whl
python -m unittest discover -s tests -v
```

CI runs the installed-wheel checks on Python 3.11 and 3.13. The local HTTPS tests
use OpenSSL to generate temporary certificates and require no production API
credentials. Use Black for Python formatting and keep changes focused.

## Maintaining API support

The [compatibility report](docs/api-compatibility.md) explains the OpenAPI snapshot,
its generator, legacy deprecations and known limitations. Verify routing and schema
changes independently; documentation coverage alone does not establish successful
live writes or credential permissions.

## Releases

See [the release maintainer guide](docs/RELEASING.md) for TestPyPI publication and
release verification. No automatic production PyPI publisher is configured.
