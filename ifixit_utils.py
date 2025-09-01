import json
import logging
import time
from typing import List, Optional, Tuple

from requests.exceptions import HTTPError, RequestException

from ifixit_api_client import IFixitAPIClient

# Configure logging to match IFixitAPIClient
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class IFixitUtils:
    """Utility class for iFixit API operations related to devices and repairability.

    This class provides methods to fetch device lists and repairability scores,
    building on top of the IFixitAPIClient. It handles pagination, error handling,
    and result storage.

    Usage:
        client = IFixitAPIClient(auth_token='your_token')
        utils = IFixitUtils(client)
        devices = utils.get_device_list()
        utils.save_repairability_scores(devices, 'scores.csv')
    """

    def __init__(self, client: IFixitAPIClient):
        """Initialize the utility class with an iFixit API client.

        Args:
            client: The IFixitAPIClient instance for API requests.
        """
        self.client = client

    def get_device_list(
        self,
        limit: int = 100,
        sleep_interval: float = 0.5
    ) -> List[str]:
        """Fetches a list of device titles from the iFixit API with pagination.

        Retrieves devices from the /categories endpoint, handling both nested
        categories (e.g., 'Asus R Series') and standalone devices.

        Args:
            limit: Number of results per page (default: 100).
            sleep_interval: Seconds to wait between requests to avoid rate limits
                (default: 0.5).

        Returns:
            A list of device titles (strings) with associated wikis.

        Raises:
            HTTPError: If an API request returns an HTTP error (e.g., 429, 500).
            RequestException: If an API request fails for other reasons.
            ValueError: If the JSON response cannot be parsed or is malformed.
        """
        devices: List[str] = []
        offset: int = 0

        data = self.client.get_categories()
        while True:
            try:
                # Log raw response for debugging
                logger.debug(
                    "Raw response for offset %d: %s",
                    offset, json.dumps(data, indent=2)
                )

                # Check if response is a dict (expected structure)
                if not isinstance(data, dict):
                    logger.error("Response is not a dict: %s", type(data))
                    break

                # Extract devices from categories
                current_devices: List[str] = []
                for category, value in data.items():
                    if isinstance(value, dict):
                        # Category with nested devices (e.g., "Asus R Series": {"Asus R510CA-OB01": null})
                        current_devices.extend(value.keys())
                    elif value is None:
                        # Standalone device (e.g., "Asus P2540UB": null)
                        current_devices.append(category)

                devices.extend(current_devices)

                logger.info(
                    "Fetched %d devices at offset %d, total: %d",
                    len(current_devices), offset, len(devices)
                )

                break

                offset += limit
                time.sleep(sleep_interval)

            except HTTPError as e:
                logger.error(
                    "HTTP error at offset %d: %s - %s",
                    offset, e.response.status_code, e.response.text
                )
                break
            except RequestException as e:
                logger.error("Request failed at offset %d: %s", offset, str(e))
                break
            except ValueError as e:
                logger.error("Failed to parse JSON at offset %d: %s", offset, str(e))
                break

        # Remove duplicates while preserving order
        seen = set()
        devices = [d for d in devices if not (d in seen or seen.add(d))]

        logger.info("Retrieved %d unique devices", len(devices))
        return devices

    def get_repairability_score(
            self,
            device: str
    ) -> Tuple[str, Optional[int]]:
        """Fetches the repairability score for a device.

        Args:
            device: The device title (e.g., 'Samsung_Galaxy_S22_Ultra').

        Returns:
            A tuple of (model_name, repairability_score). Score is None if not
            available.

        Raises:
            HTTPError: If the API request returns an HTTP error.
            RequestException: If the API request fails for other reasons.
            ValueError: If the JSON response cannot be parsed.
        """
        try:
            data = self.client.get_category_hierarchy(device_name=device, params=None)
            model = data.get("info", [{}])[0].get("value", device)
            score = data.get("repairability_score")
            return model, score
        except (HTTPError, RequestException, ValueError) as e:
            logger.error(f"Failed to fetch score for {device}: {str(e)}")
            return device, None
