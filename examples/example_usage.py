"""Example usage of the iFixit API Client."""

import logging
from ifixit_api_client import IFixitAPIClient


def main():
    logging.basicConfig(level=logging.INFO)

    # Initialize client
    client = IFixitAPIClient(
        auth_token='your_api_token',  # Replace with your token
        app_id='your_app_id',  # Optional
        log_level=logging.DEBUG,
    )

    # Example: Fetch guides
    guides = client.get_guides(limit=5)
    print('Guides:', guides)

    # Example: Fetch a specific guide
    guide = client.get_guide(guideid=1234)  # Replace with a valid ID
    print('Guide:', guide)

    # Example: Create a comment (requires auth)
    comment_data = {'text': 'This is a test comment.'}
    comment = client.create_comment(
        context='guide',
        contextid=1234,  # Replace with a valid context ID
        data=comment_data,
    )
    print('Created Comment:', comment)

    # Example: Search users
    users = client.search_users(search='test')
    print('Users:', users)

    # Example: Get current user (requires auth)
    current_user = client.get_current_user()
    print('Current User:', current_user)


if __name__ == '__main__':
    main()
