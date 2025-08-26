# iFixit API Client

A Python client for the iFixit API v2.0.

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
pip install git+https://github.com/yourusername/ifixit-api-client.git
```

### Locally
Clone the repository and install:
```bash
git clone https://github.com/yourusername/ifixit-api-client.git
cd ifixit-api-client
pip install .
```

## Usage

Initialize the client with your API token (required for authenticated endpoints):

```python
from ifixit_api_client import IFixitAPIClient

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

## API Documentation
Refer to the official iFixit API docs: [https://www.ifixit.com/api/2.0/doc/](https://www.ifixit.com/api/2.0/doc/)

Note: Always respect iFixit API rate limits and terms of service.

## Contributing
Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/YourFeature`).
3. Commit your changes (`git commit -m 'Add YourFeature'`).
4. Push to the branch (`git push origin feature/YourFeature`).
5. Open a Pull Request.

We adhere to the Google Python Style Guide. Run `black` or `yapf` for formatting.

## License
MIT License - see [LICENSE](LICENSE) for details.

## Support
For issues, open a GitHub Issue. For questions, contact via GitHub Discussions.
