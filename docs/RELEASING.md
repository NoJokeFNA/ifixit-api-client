# TestPyPI releases

The manually started **Publish to TestPyPI** workflow is
[`.github/workflows/publish-testpypi.yml`](../.github/workflows/publish-testpypi.yml).
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
