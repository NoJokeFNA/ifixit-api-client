"""Example usage of the iFixit API Client."""
import json
import logging

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


if __name__ == '__main__':
    main()
