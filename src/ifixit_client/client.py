import hashlib
import hmac
import logging
import os
import re
import warnings
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Generator, List, Optional, TypeVar, Union, cast

import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool
from urllib3.exceptions import SSLError as Urllib3SSLError

from .models import Guide

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)


def beta(func: F) -> F:
    """Decorator to mark a method as BETA.

    Emits a UserWarning each time the decorated function is called to signal
    that the API surface is experimental and may change without notice.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        warnings.warn(
            f"{func.__name__} is in BETA and may change without notice.",
            UserWarning,
            stacklevel=2,
        )
        return func(*args, **kwargs)

    return cast(F, wrapper)


def requires_token(func: F) -> F:
    """Decorator to ensure an instance has an auth token before calling.

    Assumes the decorated function is a bound method whose first argument is
    `self` and that the instance has an `auth_token` attribute.

    Raises:
        ValueError: If no auth token is present.
    """

    @wraps(func)
    def wrapper(self, *args: Any, **kwargs: Any):
        if not getattr(self, "auth_token", None):
            raise ValueError(f"{func.__name__} requires an API token.")
        return func(self, *args, **kwargs)

    return cast(F, wrapper)


def requires_admin(func: F) -> F:
    """Decorator to mark a method as requiring admin access.

    Notes:
        - This is primarily a semantic marker so tools and callers can detect
          admin-only methods via the attribute `requires_admin = True` on the
          wrapped function.
        - It enforces presence of an API token (like requires_token) but does
          not attempt to validate actual admin privileges at runtime, since that
          depends on server-side roles and tokens.

    Raises:
        ValueError: If no auth token is present on the client instance.
    """

    @wraps(func)
    def wrapper(self, *args: Any, **kwargs: Any):
        if not getattr(self, "auth_token", None):
            raise ValueError(f"{func.__name__} requires admin privileges and an API token.")
        return func(self, *args, **kwargs)

    # Semantic marker for introspection
    setattr(wrapper, "requires_admin", True)
    return cast(F, wrapper)


class Namespace(Enum):
    CATEGORY = "CATEGORY"
    ITEM = "ITEM"
    TEAM = "TEAM"
    USER = "USER"
    INFO = "INFO"
    WIKI = "WIKI"


def _normalize_fingerprint(value: str) -> str:
    """Accept an SHA-256 fingerprint, with optional colon separators."""
    if not isinstance(value, str):
        raise TypeError("certificate_fingerprint must be a SHA-256 string")
    normalized = value.strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized[len("sha256:") :]
    normalized = normalized.replace(":", "")
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError("certificate_fingerprint must contain 64 SHA-256 hex digits")
    return normalized


def _pinned_pool_class(fingerprint: str):
    """Add a pin check after ordinary TLS validation, before an API HTTP request."""

    class PinnedConnection(HTTPSConnection):
        def connect(self):
            super().connect()
            actual = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
            if not hmac.compare_digest(actual, fingerprint):
                self.close()
                raise Urllib3SSLError(
                    "Server certificate SHA-256 fingerprint does not match the configured pin"
                )

    class PinnedPool(HTTPSConnectionPool):
        ConnectionCls = PinnedConnection

    return PinnedPool


class _CertificatePinAdapter(HTTPAdapter):
    def __init__(self, fingerprint: str, **kwargs):
        self._pinned_pool = _pinned_pool_class(fingerprint)
        super().__init__(**kwargs)

    def _configure_manager(self, manager):
        # urllib3's default scheme mapping is shared; never modify it in place.
        manager.pool_classes_by_scheme = dict(manager.pool_classes_by_scheme)
        manager.pool_classes_by_scheme["https"] = self._pinned_pool

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self._configure_manager(self.poolmanager)

    def proxy_manager_for(self, *args, **kwargs):
        manager = super().proxy_manager_for(*args, **kwargs)
        self._configure_manager(manager)
        return manager

    def send(self, request, **kwargs):
        if not request.url.lower().startswith("https://"):
            raise requests.exceptions.SSLError(
                "Certificate pinning requires HTTPS, including redirects"
            )
        if not kwargs.get("verify", True):
            raise ValueError(
                "Certificate pinning requires TLS verification; supply ca_bundle for a private CA"
            )
        return super().send(request, **kwargs)


class IFixitAPIClient:
    """A Python client for the iFixit API v2.0.

    Provides authenticated, retried, and logged access to the iFixit API v2.0.

    Usage:
        client = IFixitAPIClient(auth_token="...", app_id="...")
        guides = client.get_guides(params={"limit": 10, "offset": 0})

    Notes:
        - Official docs: https://www.ifixit.com/api/2.0/doc/
        - This client retries transient failures (429, 5xx) with backoff.
        - Responses are not schema-validated; consult the API docs for shapes.
    """

    BASE_URL = 'https://www.ifixit.com/api/2.0'

    def __init__(
        self,
        auth_token: Optional[str] = None,
        app_id: Optional[str] = None,
        retries: int = 3,
        backoff_factor: float = 0.5,
        timeout: int = 30,
        log_level: int = logging.INFO,
        proxy=False,
        allow_http: bool = False,
        raise_for_status: bool = True,
        ca_bundle: Optional[Union[str, os.PathLike]] = None,
        certificate_fingerprint: Optional[str] = None,
    ):
        """Initialize the client.

        Args:
            auth_token: Authentication token for authorized requests.
            app_id: Optional app ID for the X-App-Id header.
            retries: Number of retries for failed requests.
            backoff_factor: Backoff factor for retries.
            timeout: Request timeout in seconds.
            log_level: Logging level (e.g., logging.DEBUG).
            allow_http: Allow HTTP requests when using a proxy.
            raise_for_status: Raise exceptions for HTTP error responses.
            proxy: Opt in to environment proxy settings (default: False).
            ca_bundle: PEM CA bundle file or hashed CA directory for server verification.
            certificate_fingerprint: Optional SHA-256 pin for the server's leaf certificate.
                The CA chain and hostname must also be valid. A renewed certificate
                requires updating its pin.
        """
        self.auth_token = auth_token
        self.app_id = app_id
        self.timeout = timeout
        self.proxy = proxy
        self.raise_for_status = raise_for_status
        self.ca_bundle = os.fspath(ca_bundle) if ca_bundle is not None else None
        if self.ca_bundle is not None and not os.path.exists(self.ca_bundle):
            raise FileNotFoundError(
                "CA bundle path does not exist: %s" % self.ca_bundle
            )
        self.certificate_fingerprint = (
            _normalize_fingerprint(certificate_fingerprint)
            if certificate_fingerprint is not None
            else None
        )
        logging.basicConfig(level=log_level)

        self.session = requests.Session()
        self.session.trust_env = bool(proxy)
        self.session.verify = self.ca_bundle if self.ca_bundle is not None else True
        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )

        if self.certificate_fingerprint is not None:
            adapter = _CertificatePinAdapter(
                self.certificate_fingerprint, max_retries=retry_strategy
            )
        else:
            adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        if allow_http or self.certificate_fingerprint is not None:
            self.session.mount("http://", adapter)

    def _build_headers(self) -> Dict[str, str]:
        """Construct default HTTP headers for API requests.

        Returns:
            A dictionary containing content-type, accept, and optional auth headers.
        """
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        if self.auth_token:
            headers['Authorization'] = f'api {self.auth_token}'
        if self.app_id:
            headers['X-App-Id'] = self.app_id
        return headers

    def _namespace_to_str(self, namespace: Namespace) -> str:
        """Return the string value for a Namespace enum.

        Args:
            namespace: Namespace enum.

        Raises:
            TypeError: if the provided object is not a Namespace enum.
        """
        if not isinstance(namespace, Namespace):
            raise TypeError("namespace must be a Namespace enum")
        return namespace.value

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        """Make an API request.

        Args:
            method: HTTP method (e.g., 'GET', 'POST').
            endpoint: API endpoint path.
            params: Query parameters.
            json: JSON payload for POST/PATCH/PUT.
            **kwargs: Additional requests kwargs.

        Returns:
            JSON response or None.

        Raises:
            requests.exceptions.HTTPError: For HTTP errors.
            requests.exceptions.RequestException: For other request failures.
        """
        url = f'{self.BASE_URL}/{endpoint.lstrip("/")}'
        headers = self._build_headers()
        logger.debug(
            f"Making {method} request to {url} with params={params}, " f"json={json}"
        )

        request_options = dict(kwargs)
        request_options.setdefault("timeout", self.timeout)
        if self.ca_bundle is not None:
            request_options.setdefault("verify", self.ca_bundle)

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json,
                **request_options,
            )
            if self.raise_for_status:
                response.raise_for_status()
            return response.json() if response.content else None
        except requests.exceptions.HTTPError as e:
            logger.error(
                f"HTTP error: {e.response.status_code} - " f"{e.response.text}"
            )
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise

    # --- Cart Endpoints ---

    @beta
    def get_cart_product(self, item_code: str, language_id: str) -> Dict:
        """Retrieve content linked to a store product.

        Fetches editorial content (repair guides and wikis) associated with a cart
        product.

        Args:
            item_code: Canonical numeric product code as used by the cart service
                (e.g., "1800041"). If you start from a human-facing iFixit Part Number
                (e.g., "IF180-004-1"), convert it to the numeric code before calling this
                method; conversion is intentionally left to the caller.
            language_id: Preferred language code for related content (e.g., "en",
                "de", "fr"). If localized content is unavailable, the API may return a
                fallback language or empty lists.

        Returns:
            Returns all guides and wikis associated with the product, along with information about those guides and wikis.

        Examples:
            client.get_cart_product("1800041", "en")
        """
        return self._request('GET', f'/cart/product/{item_code}/{language_id}')

    # --- Authentication Endpoints ---

    def create_user_token(self, data: Dict) -> Dict:
        """Create a user token.

        Args:
            data: Payload for token creation.

        Returns:
            Token details.
        """
        return self._request('POST', '/user/token', json=data)

    def reset_password(self, data: Dict) -> Dict:
        """Reset user password.

        Args:
            data: Payload for password reset.

        Returns:
            Response details.
        """
        return self._request('POST', '/users/reset_password', json=data)

    def create_user(self, data: Dict) -> Dict:
        """Create a new user.

        Args:
            data: User creation payload.

        Returns:
            User details.
        """
        return self._request('POST', '/users', json=data)

    def delete_user_token(self) -> None:
        """Delete the current user token."""
        return self._request('DELETE', '/user/token')

    # --- Badges Endpoints ---

    def get_badges(self) -> List[Dict]:
        """Get all badges.

        Returns:
            List of badges.
        """
        return self._request('GET', '/badges')

    def get_badge(self, badgeid: int) -> Dict:
        """Get a specific badge.

        Args:
            badgeid: Badge ID.

        Returns:
            Badge details.
        """
        return self._request('GET', f'/badges/{badgeid}')

    # --- Content Hierarchy Endpoints ---

    def get_categories(self) -> List[Dict]:
        """Get all categories.

        Returns:
            List of categories.
        """
        return self._request('GET', '/categories')

    # --- Media Endpoints ---

    def get_image(self, imageid: str) -> Dict:
        """Get an image.

        Args:
            imageid: Image ID or GUID.

        Returns:
            Image details.
        """
        return self._request('GET', f'/media/images/{imageid}')

    def get_video(self, videoid: str) -> Dict:
        """Get a video.

        Args:
            videoid: Video ID or GUID.

        Returns:
            Video details.
        """
        return self._request('GET', f'/media/videos/{videoid}')

    # --- Guides Endpoints ---

    def get_guides(
        self,
        params: Optional[Dict] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict]:
        """Get a list of guides.

        Args:
            params: Query parameters for filtering, pagination, etc.
            limit: Optional page size, overriding params['limit'].
            offset: Optional offset, overriding params['offset'].

        Returns:
            List of guides.
        """
        query = dict(params) if params is not None else None
        for name, value, minimum in [("limit", limit, 1), ("offset", offset, 0)]:
            if value is not None:
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < minimum
                ):
                    raise ValueError("%s must be an integer >= %d" % (name, minimum))
                if query is None:
                    query = {}
                query[name] = value
        return self._request("GET", "/guides", params=query)

    def get_all_guides(
        self,
        page_size: int = 100,
        limit: Optional[int] = None,
        raw: bool = False,
        parser: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Generator[Any, None, None]:
        """Stream all guides by handling pagination, with optional parsing control.

        Iterates through pages from GET /guides and yields one item at a time to
        keep memory usage low. By default, each item is parsed into a Guide model.

        Performance tuning:
        - Set raw=True to yield raw dicts (skips Pydantic parsing for speed).
        - Provide a custom parser callable to transform each dict (takes precedence
          over ``raw``), e.g., parser=lambda d: MyGuide.from_dict(d).

        Args:
            page_size: Number of results per page ("limit" query parameter).
            limit: Maximum number of guides to yield; zero makes no request.
            raw: If True, yield raw dicts instead of Guide models.
            parser: Optional callable to transform each guide dict before yielding.

        Yields:
            - Guide models by default.
            - Raw dicts if raw=True.
            - Results of parser(dict) if parser is provided.
        """
        if (
            not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or page_size < 1
        ):
            raise ValueError("page_size must be a positive integer")
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 0
        ):
            raise ValueError("limit must be a non-negative integer or None")
        offset = 0
        while limit is None or offset < limit:
            requested = page_size if limit is None else min(page_size, limit - offset)
            batch = self.get_guides(params={"limit": requested, "offset": offset})
            if not batch:
                break
            for index, guide_dict in enumerate(batch):
                if limit is not None and offset + index >= limit:
                    return
                if parser is not None:
                    yield parser(guide_dict)
                elif raw:
                    yield guide_dict
                else:
                    yield Guide(**guide_dict)
            offset += len(batch)
            logger.info(
                "Fetched %d guides (streamed), total offset now: %d", len(batch), offset
            )

    def get_guide(self, guideid: int) -> Dict:
        """Get a specific guide.

        Args:
            guideid: Guide ID.

        Returns:
            Guide details.
        """
        return self._request('GET', f'/guides/{guideid}')

    def get_guide_tags(self, guideid: int) -> List[str]:
        """Get tags for a guide.

        Args:
            guideid: Guide ID.

        Returns:
            List of tags.
        """
        return self._request('GET', f'/guides/{guideid}/tags')

    def create_guide(self, data: Dict) -> Dict:
        """Create a new guide.

        Args:
            data: Guide creation payload.

        Returns:
            Created guide details.
        """
        return self._request('POST', '/guides', json=data)

    def update_guide(self, guideid: int, data: Dict, revisionid: int) -> Dict:
        """Update an existing guide.

        PATCH /guides/{guideid}

        Updates only the provided fields of an existing guide. The current
        revision ID must be supplied via the revisionid query parameter per API.

        Args:
            guideid: Guide to update (numeric guide ID).
            data: JSON body containing only the fields to update. See API docs
                for supported fields such as category, type, title, introduction,
                flags, conclusion, time_required, difficulty, image,
                prerequisites, prerequisite_releases, documents,
                featured_documentid, public, parts, tools, author.
            revisionid: Current revision ID of the guide (required by the API).

        Returns:
            The updated guide object.
        """
        params = {'revisionid': revisionid}
        return self._request('PATCH', f'/guides/{guideid}', json=data, params=params)

    def delete_guide(self, guideid: int, revisionid: int) -> None:
        """Permanently delete a guide.

        DELETE /guides/{guideid}

        Args:
            guideid: Numeric guide ID.
            revisionid: Current revision ID of the guide (required by the API).
        """
        params = {'revisionid': revisionid}
        return self._request('DELETE', f'/guides/{guideid}', params=params)

    def restore_guide(self, guideid: int, langid: str) -> Dict:
        """Restore a guide.

        Args:
            guideid: Guide ID.
            langid: Language ID.

        Returns:
            Restored guide details.
        """
        return self._request('POST', f'/guides/{guideid}/{langid}/restore')

    def complete_guide(self, guideid: int) -> Dict:
        """Mark a guide as completed.

        Args:
            guideid: Guide ID.

        Returns:
            Response details.
        """
        return self._request('PUT', f'/guides/{guideid}/completed')

    def uncomplete_guide(self, guideid: int) -> None:
        """Unmark a guide as completed.

        Args:
            guideid: Guide ID.
        """
        return self._request('DELETE', f'/guides/{guideid}/completed')

    def make_guide_public(self, guideid: int) -> Dict:
        """Make a guide public.

        Args:
            guideid: Guide ID.

        Returns:
            Response details.
        """
        return self._request('PUT', f'/guides/{guideid}/public')

    @requires_token
    def make_guide_private(self, guideid: int) -> Dict:
        """Make a guide private.

        Args:
            guideid: Guide ID.

        Returns:
            Response details.
        """
        return self._request('DELETE', f'/guides/{guideid}/public')

    def create_guide_step(self, guideid: int, data: Dict) -> Dict:
        """Create a step in a guide.

        Args:
            guideid: Guide ID.
            data: Step payload.

        Returns:
            Created step details.
        """
        return self._request('POST', f'/guides/{guideid}/steps', json=data)

    def update_guide_step(self, guideid: int, stepid: int, data: Dict) -> Dict:
        """Update a guide step.

        Args:
            guideid: Guide ID.
            stepid: Step ID.
            data: Update payload.

        Returns:
            Updated step details.
        """
        return self._request('PATCH', f'/guides/{guideid}/steps/{stepid}',
                             json=data)

    def delete_guide_step(self, guideid: int, stepid: int) -> None:
        """Delete a guide step.

        Args:
            guideid: Guide ID.
            stepid: Step ID.
        """
        return self._request('DELETE', f'/guides/{guideid}/steps/{stepid}')

    def update_guide_step_order(self, guideid: int, data: Dict) -> Dict:
        """Update the order of steps in a guide.

        Args:
            guideid: Guide ID.
            data: Step order payload.

        Returns:
            Response details.
        """
        return self._request('PUT', f'/guides/{guideid}/steporder', json=data)

    def get_guide_users(self, guideid: int) -> List[Dict]:
        """Get users associated with a guide.

        Args:
            guideid: Guide ID.

        Returns:
            List of users.
        """
        return self._request('GET', f'/guides/{guideid}/users')

    def add_user_to_guide(self, guideid: int, userid: int) -> Dict:
        """Add a user to a guide.

        Args:
            guideid: Guide ID.
            userid: User ID.

        Returns:
            Response details.
        """
        return self._request('PUT', f'/guides/{guideid}/users/{userid}')

    def remove_user_from_guide(self, guideid: int, userid: int) -> None:
        """Remove a user from a guide.

        Args:
            guideid: Guide ID.
            userid: User ID.
        """
        return self._request('DELETE', f'/guides/{guideid}/users/{userid}')

    def get_guide_teams(self, guideid: int) -> List[Dict]:
        """Get teams associated with a guide.

        Args:
            guideid: Guide ID.

        Returns:
            List of teams.
        """
        return self._request('GET', f'/guides/{guideid}/teams')

    def add_team_to_guide(self, guideid: int, teamid: int) -> Dict:
        """Add a team to a guide.

        Args:
            guideid: Guide ID.
            teamid: Team ID.

        Returns:
            Response details.
        """
        return self._request('PUT', f'/guides/{guideid}/teams/{teamid}')

    def remove_team_from_guide(self, guideid: int, teamid: int) -> None:
        """Remove a team from a guide.

        Args:
            guideid: Guide ID.
            teamid: Team ID.
        """
        return self._request('DELETE', f'/guides/{guideid}/teams/{teamid}')

    def get_guide_releases(self) -> List[Dict]:
        """Get all guide releases.

        Returns:
            List of releases.
        """
        return self._request('GET', '/guides/releases')

    def delete_guide_release(self, releaseid: int) -> None:
        """Delete a guide release.

        Args:
            releaseid: Release ID.
        """
        return self._request('DELETE', f'/guides/releases/{releaseid}')

    def get_guide_specific_releases(self, guideid: int) -> List[Dict]:
        """Get releases for a specific guide.

        Args:
            guideid: Guide ID.

        Returns:
            List of releases.
        """
        return self._request('GET', f'/guides/{guideid}/releases')

    @beta
    @requires_token
    def create_guide_release(self, data: Dict) -> Dict:
        """Create a guide release.

        Args:
            data: Release payload.

        Returns:
            Created release details.
        """
        return self._request('POST', '/guides/releases', json=data)

    def update_guide_release(self, releaseid: int, data: Dict) -> Dict:
        """Update a guide release.

        Args:
            releaseid: Release ID.
            data: Update payload.

        Returns:
            Updated release details.
        """
        return self._request('PATCH', f'/guides/releases/{releaseid}',
                             json=data)

    def add_guide_tag(self, guideid: int, data: Dict) -> Dict:
        """Add a tag to a guide.

        Args:
            guideid: Guide ID.
            data: Tag payload.

        Returns:
            Response details.
        """
        return self._request('PUT', f'/guides/{guideid}/tag', json=data)

    def remove_guide_tag(self, guideid: int, data: Dict) -> None:
        """Remove a tag from a guide.

        Args:
            guideid: Guide ID.
            data: Tag payload.
        """
        return self._request('DELETE', f'/guides/{guideid}/tag', json=data)

    # --- Comments Endpoints ---

    def get_comments(self) -> List[Dict]:
        """Get all comments.

        Returns:
            List of comments.
        """
        return self._request('GET', '/comments')

    def get_comment(self, commentid: int) -> Dict:
        """Get a specific comment.

        Args:
            commentid: Comment ID.

        Returns:
            Comment details.
        """
        return self._request('GET', f'/comments/{commentid}')

    def create_comment(self, context: str, contextid: int, data: Dict) -> Dict:
        """Create a comment.

        Args:
            context: Context type (e.g., 'guide').
            contextid: Context ID.
            data: Comment payload.

        Returns:
            Created comment details.
        """
        return self._request('POST', f'/comments/{context}/{contextid}',
                             json=data)

    def update_comment(self, commentid: int, data: Dict) -> Dict:
        """Update a comment.

        Args:
            commentid: Comment ID.
            data: Update payload.

        Returns:
            Updated comment details.
        """
        return self._request('PATCH', f'/comments/{commentid}', json=data)

    def delete_comment(self, commentid: int) -> None:
        """Delete a comment.

        Args:
            commentid: Comment ID.
        """
        return self._request('DELETE', f'/comments/{commentid}')

    # --- Suggest Endpoints ---

    def suggest(self, query: str, doctypes: str = 'all') -> List[Dict]:
        """Get suggestions based on a query.

        Args:
            query: Search query.
            doctypes: Document types (default: 'all').

        Returns:
            List of suggestions.
        """
        params = {'doctypes': doctypes}
        return self._request('GET', f'/suggest/{query}', params=params)

    # --- Stories Endpoints ---

    def get_stories(self) -> List[Dict]:
        """Get all stories.

        Returns:
            List of stories.
        """
        return self._request('GET', '/stories')

    def get_story(self, storyid: int) -> Dict:
        """Get a specific story.

        Args:
            storyid: Story ID.

        Returns:
            Story details.
        """
        return self._request('GET', f'/stories/{storyid}')

    def create_story(self, data: Dict) -> Dict:
        """Create a story.

        Args:
            data: Story payload.

        Returns:
            Created story details.
        """
        return self._request('POST', '/stories', json=data)

    def update_story(self, storyid: int, data: Dict) -> Dict:
        """Update a story.

        Args:
            storyid: Story ID.
            data: Update payload.

        Returns:
            Updated story details.
        """
        return self._request('PATCH', f'/stories/{storyid}', json=data)

    # --- Tags Endpoints ---

    def get_tags(self) -> List[Dict]:
        """Get all tags.

        Returns:
            List of tags.
        """
        return self._request('GET', '/tags')

    def add_wiki_tag(self, namespace: Namespace, title: str, tag: str) -> Dict:
        """Add a tag to a wiki.

        Args:
            namespace: Wiki namespace. Possible values: WIKI, CATEGORY, INFO, ITEM, USER, TEAM.
            title: Display title of the wiki to tag.
            tag: The name of the tag to add.

        Returns:
            Response details.
        """
        return self._request('PUT', f"/wikis/{self._namespace_to_str(namespace)}/{title}/tag", json={"tag": tag})

    @requires_token
    def remove_wiki_tag(self, namespace: Namespace, title: str, tag: str) -> None:
        """Remove a tag from a wiki.

        Args:
            namespace: Wiki namespace. Possible values: WIKI, CATEGORY, INFO, ITEM, USER, TEAM.
            title: Display title of the wiki to remove the tag from.
            tag: The name of the tag to remove.
        """
        return self._request('DELETE', f"/wikis/{self._namespace_to_str(namespace)}/{title}/tag", json={"tag": tag})

    # --- Teams Endpoints ---

    def get_teams(self) -> List[Dict]:
        """Get all teams.

        Returns:
            List of teams.
        """
        return self._request('GET', '/teams')

    def get_team_members(self, teamid: int) -> List[Dict]:
        """Get members of a team.

        Args:
            teamid: Team ID.

        Returns:
            List of members.
        """
        return self._request('GET', f'/teams/{teamid}')

    def add_user_to_team(self, teamid: int, userid: int) -> Dict:
        """Add a user to a team.

        Args:
            teamid: Team ID.
            userid: User ID.

        Returns:
            Response details.
        """
        return self._request('PUT', f'/teams/{teamid}/users/{userid}')

    def remove_user_from_team(self, teamid: int, userid: int) -> None:
        """Remove a user from a team.

        Args:
            teamid: Team ID.
            userid: User ID.
        """
        return self._request('DELETE', f'/teams/{teamid}/users/{userid}')

    # --- Users Endpoints ---

    def get_users(self) -> List[Dict]:
        """Get all users.

        Returns:
            List of users.
        """
        return self._request('GET', '/users')

    def search_users(self, search: str) -> List[Dict]:
        """Search for users.

        Args:
            search: Search query.

        Returns:
            List of matching users.
        """
        return self._request('GET', f'/users/search/{search}')

    def get_user(self, userid: int) -> Dict:
        """Get a specific user.

        Args:
            userid: User ID.

        Returns:
            User details.
        """
        return self._request('GET', f'/users/{userid}')

    def get_user_by_sso(self, sso_userid: str) -> Dict:
        """Get a user by SSO ID.

        Args:
            sso_userid: SSO user ID.

        Returns:
            User details.
        """
        return self._request('GET', f'/users/sso/{sso_userid}')

    def get_user_by_email(self, email: str) -> Dict:
        """Get a user by email.

        Args:
            email: User email.

        Returns:
            User details.
        """
        return self._request('GET', f'/users/email/{email}')

    def get_user_badges(self, userid: int) -> List[Dict]:
        """Get badges for a user.

        Args:
            userid: User ID.

        Returns:
            List of badges.
        """
        return self._request('GET', f'/users/{userid}/badges')

    def get_user_favorite_guides(self, userid: int) -> List[Dict]:
        """Get favorite guides for a user.

        Args:
            userid: User ID.

        Returns:
            List of favorite guides.
        """
        return self._request('GET', f'/users/{userid}/favorites/guides')

    def get_user_guides(self, userid: int) -> List[Dict]:
        """Get guides for a user.

        Args:
            userid: User ID.

        Returns:
            List of guides.
        """
        return self._request('GET', f'/users/{userid}/guides')

    def get_user_completions(self, userid: int) -> List[Dict]:
        """Get completions for a user.

        Args:
            userid: User ID.

        Returns:
            List of completions.
        """
        return self._request('GET', f'/users/{userid}/completions')

    @requires_token
    def get_current_user(self) -> Dict:
        """Get the current authenticated user.

        Returns:
            User details.
        """
        return self._request('GET', '/user')

    @requires_token
    def get_current_user_badges(self) -> List[Dict]:
        """Get badges for the current user.

        Returns:
            List of badges.
        """
        return self._request('GET', '/user/badges')

    @requires_token
    def get_current_user_favorite_guides(self) -> List[Dict]:
        """Get favorite guides for the current user.

        Returns:
            List of favorite guides.
        """
        return self._request('GET', '/user/favorites/guides')

    @requires_token
    def favorite_guide(self, guideid: int) -> Dict:
        """Favorite a guide for the current user.

        Args:
            guideid: Guide ID.

        Returns:
            Response details.
        """
        return self._request('PUT', f'/user/favorites/guides/{guideid}')

    @requires_token
    def unfavorite_guide(self, guideid: int) -> None:
        """Unfavorite a guide for the current user.

        Args:
            guideid: Guide ID.
        """
        return self._request('DELETE', f'/user/favorites/guides/{guideid}')

    @requires_token
    def get_current_user_guides(self) -> List[Dict]:
        """Get guides for the current user.

        Returns:
            List of guides.
        """
        return self._request('GET', '/user/guides')

    @requires_token
    def get_current_user_flags(self) -> List[Dict]:
        """Get flags for the current user.

        Returns:
            List of flags.
        """
        return self._request('GET', '/user/flags')

    @requires_token
    def get_current_user_completions(self) -> List[Dict]:
        """Get completions for the current user.

        Returns:
            List of completions.
        """
        return self._request('GET', '/user/completions')

    @requires_token
    def get_current_user_images(self) -> List[Dict]:
        """Get images for the current user.

        Returns:
            List of images.
        """
        return self._request('GET', '/user/media/images')

    @requires_token
    def upload_user_image(self, data: Dict) -> Dict:
        """Upload an image for the current user.

        Args:
            data: Image payload (e.g., base64-encoded).

        Returns:
            Uploaded image details.
        """
        return self._request('POST', '/user/media/images', json=data)

    @requires_token
    def delete_user_images(self, imageids: str) -> None:
        """Delete images for the current user.

        Args:
            imageids: Comma-separated image IDs.
        """
        return self._request('DELETE', f'/user/media/images/{imageids}')

    @requires_token
    def update_user_image(self, imageid: str, data: Dict) -> Dict:
        """Update a user image.

        Args:
            imageid: Image ID or GUID.
            data: Update payload.

        Returns:
            Updated image details.
        """
        return self._request('POST', f'/user/media/images/{imageid}',
                             json=data)

    @requires_token
    def get_current_user_videos(self) -> List[Dict]:
        """Get videos for the current user.

        Returns:
            List of videos.
        """
        return self._request('GET', '/user/media/videos')

    @requires_token
    def update_user(self, userid: int, data: Dict) -> Dict:
        """Update a user.

        Args:
            userid: User ID.
            data: Update payload.

        Returns:
            Updated user details.
        """
        return self._request('PATCH', f'/users/{userid}', json=data)

    # --- Wikis Endpoints ---

    def get_category(
        self, device_name: Optional[str] = None, params: Optional[dict] = None
    ) -> Dict:
        """Get the category hierarchy.

        Args:
            device_name: Optional device name to filter the hierarchy.
            params: Optional parameters to customize the response.

        Returns:
            Hierarchy details.
        """
        endpoint = "/wikis/CATEGORY"
        if device_name:
            endpoint += f"/{device_name}"
        if params is None and not device_name:
            params = {"display": "hierarchy"}
        return self._request("GET", endpoint, params=params)

    def get_wikis(self, namespace: Namespace) -> List[Dict]:
        """Get wikis in a namespace.

        Args:
            namespace: Wiki namespace.

        Returns:
            List of wikis.
        """
        return self._request('GET', f"/wikis/{self._namespace_to_str(namespace)}")

    def get_wiki(self, namespace: Namespace, title: str) -> Dict:
        """Get a specific wiki.

        Args:
            namespace: Wiki namespace.
            title: Wiki title.

        Returns:
            Wiki details.
        """
        return self._request('GET', f"/wikis/{self._namespace_to_str(namespace)}/{title}")

    def get_wiki_tags(self, namespace: Namespace, title: str) -> List[str]:
        """Get tags for a wiki.

        Args:
            namespace: Wiki namespace.
            title: Wiki title.

        Returns:
            List of tags.
        """
        return self._request('GET', f"/wikis/{self._namespace_to_str(namespace)}/{title}/tags")

    def get_category_children(self, title: str) -> List[Dict]:
        """Get children of a category.

        Args:
            title: Category title.

        Returns:
            List of children.
        """
        return self._request('GET', f'/wikis/CATEGORY/{title}/children')

    @beta
    def get_category_identification(self, title: str) -> str:
        """Get the HTML source of the identification section of a device wiki.

        Args:
            title: Title of the device wiki to retrieve the identification section from. The identification section
            of a wiki contains 'Identification' in the heading. If there are multiple headings containing
            'Identification', the first match is selected. Output contains all content AFTER the matched heading and
            BEFORE the next heading of the same level (h2, h3, etc.) or the end of the wiki, whichever comes first.

        Returns:
            HTML content of the identification section.
        """
        return self._request('GET', f'/wikis/CATEGORY/{title}/identification')

    def create_wiki(self, data: Dict) -> Dict:
        """Create a new wiki.

        Args:
            data: Wiki creation payload.

        Returns:
            Created wiki details.
        """
        return self._request('POST', '/wikis', json=data)

    def update_wiki(self, namespace: Namespace, title: str, data: Dict,
                    revisionid: Optional[int] = None) -> Dict:
        """Update a wiki.

        Args:
            namespace: Wiki namespace.
            title: Wiki title.
            data: Update payload.
            revisionid: Optional revision ID.

        Returns:
            Updated wiki details.
        """
        params = {'revisionid': revisionid} if revisionid else None
        return self._request('PATCH', f"/wikis/{self._namespace_to_str(namespace)}/{title}",
                             json=data, params=params)

    def delete_wiki(self, namespace: Namespace, title: str) -> None:
        """Delete a wiki.

        Args:
            namespace: Wiki namespace.
            title: Wiki title.
        """
        return self._request('DELETE', f"/wikis/{self._namespace_to_str(namespace)}/{title}")

    def revert_wiki(self, namespace: Namespace, title: str, data: Dict) -> Dict:
        """Revert a wiki to a previous state.

        Args:
            namespace: Wiki namespace.
            title: Wiki title.
            data: Revert payload.

        Returns:
            Response details.
        """
        return self._request('POST', f"/wikis/{self._namespace_to_str(namespace)}/{title}/revert",
                             json=data)

    def set_wiki_parent(self, title: str, data: Dict) -> Dict:
        """Set the parent for a category wiki.

        Args:
            title: Category title.
            data: Parent payload.

        Returns:
            Response details.
        """
        return self._request('PUT', f'/wikis/CATEGORY/{title}/parent',
                             json=data)

    # --- User View History Endpoints ---

    def get_user_view_history(self, userid: int) -> List[Dict]:
        """Get view history for a user.

        Args:
            userid: User ID.

        Returns:
            List of view history entries.
        """
        return self._request('GET', f'/user_view_history/user/{userid}')

    def get_document_view_history(self, doc_type: str, docid: int) -> List[Dict]:
        """Get view history for a document.

        Args:
            doc_type: Document type.
            docid: Document ID.

        Returns:
            List of view history entries.
        """
        return self._request('GET', f'/user_view_history/{doc_type}/{docid}')

    # --- Documents Endpoints ---

    @beta
    def get_document(self, id_or_guid: str) -> Dict:
        """Get a document.

        Args:
            id_or_guid: Document ID or GUID.

        Returns:
            Document details.
        """
        return self._request('GET', f'/documents/{id_or_guid}')
