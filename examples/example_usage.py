"""Example usage of the iFixit API Client."""
import json
import logging
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from ifixit_client import IFixitAPIClient


def main():
    logging.basicConfig(level=logging.INFO)

    # Initialize client
    client = IFixitAPIClient(
        # auth_token='your_api_token',  # Replace with your token
        # app_id='your_app_id',  # Optional
        log_level=logging.DEBUG,
        proxy=True,
        allow_http=True
    )

    # Example: Fetch guides
    guides = list(client.get_all_guides(page_size=5, limit=5))
    print('Guides:', guides)

    # Example get 3 easy guides
    # easy_guides = client.get_all_guides()
    # print(len(easy_guides))

    # Example: Fetch a specific guide
    # guide = client.get_guide(guideid=1234)  # Replace with a valid ID
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
    # users = client.search_users(search='test')
    # print('Users:', users)

    # Example: Suggest
    # suggest = client.suggest(query='Pro', doctypes='device')
    # print('Suggest:', json.dumps(suggest, indent=2, ensure_ascii=False))

    # client.remove_wiki_tag(namespace=Namespace.WIKI, title='test', tag='asd')

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
