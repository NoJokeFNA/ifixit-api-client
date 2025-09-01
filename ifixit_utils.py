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

    def key_occurrences_in_list(self, lst):
        from collections import Counter
        c = Counter()
        for item in lst:
            if isinstance(item, dict):
                for k in item.keys():
                    c[k] += 1
            else:
                c[f"__NON_DICT__:{type(item).__name__}"] += 1
        return c

    def safe_deep_merge_dicts(self, dicts):
        result = {}
        for d in dicts:
            if not isinstance(d, dict):
                continue
            for k, v in d.items():
                if k not in result:
                    result[k] = v
                else:
                    existing = result[k]
                    if isinstance(existing, dict) and isinstance(v, dict):
                        result[k] = self.safe_deep_merge_dicts([existing, v])
                    elif existing == v:
                        result[k] = existing
                    else:
                        if isinstance(existing, list):
                            comb = existing
                        else:
                            comb = [existing]
                        if isinstance(v, list):
                            for x in v:
                                if x not in comb:
                                    comb.append(x)
                        else:
                            if v not in comb:
                                comb.append(v)
                        result[k] = comb
        return result

    def analyze_and_merge_data(self, data):
        metrics_before = {}
        metrics_after = {}
        merged = data

        metrics_before['top_level_len'] = len(data) if isinstance(data, (dict, list)) else 0
        metrics_before['keys_all_levels'] = self.count_keys(data)
        metrics_before['leaves'] = self.count_leaves(data)

        if isinstance(data, list):
            occ = self.key_occurrences_in_list(data)
            logger.debug("Top key occurrences: %s", occ.most_common(10))
            dict_items = [item for item in data if isinstance(item, dict)]
            merged = self.safe_deep_merge_dicts(dict_items)
            metrics_after['top_level_len'] = len(merged)
            metrics_after['keys_all_levels'] = self.count_keys(merged)
            metrics_after['leaves'] = self.count_leaves(merged)
        elif isinstance(data, dict):
            metrics_after = metrics_before.copy()
        else:
            metrics_after = metrics_before.copy()

        return metrics_before, metrics_after, merged

    def _collect_devices_from_dict(self, d):
        devices = []
        if not isinstance(d, dict):
            return devices
        for k, v in d.items():
            if isinstance(v, dict):
                devices.extend(self._collect_devices_from_dict(v))
            elif isinstance(v, list):
                for el in v:
                    if isinstance(el, dict):
                        devices.extend(self._collect_devices_from_dict(el))
            else:
                # v is None or scalar -> k is a device/model
                devices.append(k)
        return devices

    def get_device_counts(self, pages=None):
        def _count_keys_occurrences(obj):
            if isinstance(obj, dict):
                total = len(obj)
                for v in obj.values():
                    total += _count_keys_occurrences(v)
                return total
            if isinstance(obj, list):
                return sum(_count_keys_occurrences(v) for v in obj)
            return 0

        def _count_leaves(obj):
            if isinstance(obj, dict):
                return sum(_count_leaves(v) for v in obj.values())
            if isinstance(obj, list):
                return sum(_count_leaves(v) for v in obj)
            return 1

        def _collect_key_names(obj, out_set):
            if isinstance(obj, dict):
                out_set.update(obj.keys())
                for v in obj.values():
                    _collect_key_names(v, out_set)
            elif isinstance(obj, list):
                for el in obj:
                    _collect_key_names(el, out_set)

        # if pages not provided, fetch single page
        if pages is None:
            data = self.client.get_categories()
            pages = [data] if isinstance(data, dict) else (data if isinstance(data, list) else [data])

        # normalize: ensure list of dicts/pages
        pages_list = [p for p in pages]

        per_page = []
        total_keys_occurrences = 0
        total_leaves = 0
        unique_keys = set()

        for idx, p in enumerate(pages_list):
            try:
                keys_occ = _count_keys_occurrences(p)
                leaves = _count_leaves(p)
                top_len = len(p) if isinstance(p, (dict, list)) else 0
                per_page.append({"index": idx, "top_len": top_len, "keys_occurrences": keys_occ, "leaves": leaves})
                total_keys_occurrences += keys_occ
                total_leaves += leaves
                _collect_key_names(p, unique_keys)
            except Exception:
                per_page.append({"index": idx, "error": "count failed"})

        # merged comparison (may dedupe keys)
        dict_items = [p for p in pages_list if isinstance(p, dict)]
        merged = self.safe_deep_merge_dicts(dict_items) if dict_items else {}
        merged_keys_all_levels = _count_keys_occurrences(merged) if merged else 0

        result = {
            "per_page": per_page,
            "total_keys_occurrences": total_keys_occurrences,
            "total_leaves_occurrences": total_leaves,
            "merged_keys_all_levels": merged_keys_all_levels,
            "unique_key_names": len(unique_keys),
            "delta_occ_vs_merged": total_keys_occurrences - merged_keys_all_levels
        }

        logger.info("Verbose counts: total_occ=%d merged_keys=%d unique_keys=%d delta=%d",
                    total_keys_occurrences, merged_keys_all_levels, len(unique_keys),
                    result["delta_occ_vs_merged"])
        return result

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
        self.get_device_counts()

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
