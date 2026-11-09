"""Read-only example: install the package and set IFIXIT_TOKEN before running."""

import os

from ifixit_client import IFixitAPIClient


def main():
    client = IFixitAPIClient(api_key=os.environ["IFIXIT_TOKEN"])
    for guide in client.get_all_guides(page_size=5, limit=5, raw=True):
        print(guide["title"], guide["url"])


if __name__ == "__main__":
    main()
