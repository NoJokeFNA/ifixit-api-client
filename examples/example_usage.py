"""Example usage of the iFixit API Client."""
import json
import logging
import time
from typing import List

from requests import RequestException

from ifixit_api_client import IFixitAPIClient
from ifixit_utils import IFixitUtils


def main():
    logging.basicConfig(level=logging.INFO)

    # Initialize client
    client = IFixitAPIClient(
        # auth_token='your_api_token',  # Replace with your token
        # app_id='your_app_id',  # Optional
        log_level=logging.DEBUG,
    )

    ifixit_utils = IFixitUtils(client)

    # Example: Fetch guides
    guides = client.get_guides(limit=1)
    # print('Guides:', json.dumps(guides, indent=2, ensure_ascii=False))

    # Example get 3 easy guides
    # easy_guides = client.get_all_guides()
    # print(len(easy_guides))

    # Example: Fetch a specific guide
    guide = client.get_guide(guideid=1234)  # Replace with a valid ID
    # print('Guide:', guide)

    # Example: Create a comment (requires auth)
    # comment_data = {'text': 'This is a test comment.'}
    # comment = client.create_comment(
    #    context='guide',
    #    contextid=1234,  # Replace with a valid context ID
    #    data=comment_data,
    # )
    # print('Created Comment:', comment)

    # Example: Search users
    users = client.search_users(search='test')
    # print('Users:', users)

    # Example: Suggest
    suggest = client.suggest(query='Pro', doctypes='device')
    # print('Suggest:', json.dumps(suggest, indent=2, ensure_ascii=False))

    # Example: Durability score
    device_data = client.get_category_hierarchy(device_name='Samsung_Galaxy_S22_Ultra', params=None)
    score = device_data.get("repairability_score", None)
    # print('Device data:', json.dumps(device_data, indent=2, ensure_ascii=False))
    # print('Repairability Score:', score)

    # Example: Get all devices in a category
    devices = ifixit_utils.get_device_list()
    print('Devices:', json.dumps(devices, indent=2, ensure_ascii=False))

    # Example: Get current user (requires auth)
    # current_user = client.get_current_user()
    # print('Current User:', current_user)

    # Example: Create user token
    # token = client.create_user_token(data={
    #     "email": "",
    #     "password": ""
    # })
    # print('Token:', token)


def get_device_list(
    client: IFixitAPIClient,
    limit: int = 100,
    sleep_interval: float = 5.0
) -> List[str]:
    """Fetch a list of device titles from the iFixit API with pagination.

    Args:
        client: The iFixit API client instance.
        limit: Number of results per page (default: 100).
        sleep_interval: Seconds to wait between requests to avoid rate limits
            (default: 5.0).

    Returns:
        A list of device titles (strings) that have associated wikis.

    Raises:
        RequestException: If an API request fails.
        ValueError: If the JSON response cannot be parsed or is malformed.
    """
    devices: List[str] = []
    offset: int = 0

    while True:
        try:
            # Fetch the current page of devices
            params = {"limit": limit, "offset": offset}
            data = client.get_category_hierarchy(params=params)

            # Extract device titles from the response
            items = data.get("data", []) if isinstance(data, dict) else data
            if not isinstance(items, list):
                print("Unexpected response format: 'data' is not a list")
                break

            current_devices = [
                item["title"] for item in items
                if isinstance(item, dict) and "title" in item
            ]
            devices.extend(current_devices)

            print(
                f"Fetched {len(current_devices)} devices at offset {offset} "
                f"(total: {len(devices)})"
            )

            # Check if there are more pages
            if len(current_devices) < limit:
                break

            offset += limit
            time.sleep(sleep_interval)
        except RequestException as e:
            print(f"API request failed at offset {offset}: {e}")
            break
        except ValueError as e:
            print(f"Failed to parse JSON response at offset {offset}: {e}")
            break

    return devices


if __name__ == '__main__':
    main()
