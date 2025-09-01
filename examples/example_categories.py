"""Fetches and processes iFixit device data, including repairability scores.

This script retrieves device hierarchies for specified categories, collects leaf
device names, and fetches repairability scores concurrently with a progress bar.
Non-critical errors (e.g., 404s) are suppressed to maintain clean output.
Results are written to JSON files.
"""

import argparse
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Dict, Iterable, List, Optional, Set, Tuple, TypeAlias

import tqdm

from ifixit_api_client import IFixitAPIClient

# Configure logging
logger = logging.getLogger(__name__)
log_level = logging.DEBUG if __import__("os").getenv("DEBUG") else logging.INFO


class Suppress404Filter(logging.Filter):
    """Filters out HTTP 404 error logs from ifixit_api_client unless in debug mode."""

    def filter(self, record: logging.LogRecord) -> bool:
        if log_level == logging.DEBUG:
            return True
        return not ("ifixit_api_client" in record.name and "HTTP error: 404" in record.getMessage())


logging.basicConfig(level=log_level)
logging.getLogger("ifixit_api_client").addFilter(Suppress404Filter())

JsonValue: TypeAlias = Dict[str, "JsonValue"] | List["JsonValue"] | str | int | float | bool | None


def _is_metadata_key(key: str) -> bool:
    """Returns whether a key is considered metadata and should be skipped."""
    metadata_keys = {
        "attrs",
        "contents_json",
        "image",
        "inheritedFrom",
        "parts",
        "repairability_score",
        "source_revisionid",
    }
    return key in metadata_keys


def _collect_leaf_device_names(node: JsonValue, excluded_keys: Set[str] | None = None) -> Iterable[str]:
    """Yields leaf device names under a node.

    A leaf device is represented by:
      - A dict entry with value None: {"Asus ROG Phone 6": None}
      - A string inside a list: {"Some Series": ["Model A", "Model B"]}
      - Nested dicts are traversed recursively.

    Args:
        node: The current JSON-like node (dict, list, etc.).
        excluded_keys: Set of keys (category names) to exclude entirely.

    Yields:
        Leaf device names as strings.
    """
    excluded_keys = excluded_keys or set()
    if isinstance(node, dict):
        for key, value in node.items():
            if _is_metadata_key(key) or key in excluded_keys:
                continue
            if value is None:
                yield key
            elif isinstance(value, dict):
                yield from _collect_leaf_device_names(value, excluded_keys)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield from _collect_leaf_device_names(item, excluded_keys)
                    elif isinstance(item, str):
                        yield item
                    elif item is None:
                        yield key
    elif isinstance(node, list):
        for item in node:
            yield from _collect_leaf_device_names(item, excluded_keys)


def _find_and_collect_for_targets(
        node: JsonValue,
        target_categories: Iterable[str],
        exclude_map: Dict[str, Set[str]] | None = None,
) -> Dict[str, List[str]]:
    """Finds target categories in the tree and collects all leaf devices under them.

    Scans the entire structure. When a key matches a target category, all descendant
    leaves are collected, respecting category-specific exclusions.

    Args:
        node: The root node of the hierarchy.
        target_categories: Category names to search for.
        exclude_map: Mapping of target_category -> set of subtree keys to exclude.

    Returns:
        Dictionary mapping target category to sorted list of leaf device names.
    """
    targets_set: Set[str] = set(target_categories)
    collected: Dict[str, List[str]] = {t: [] for t in targets_set}
    exclude_map = exclude_map or {}

    def dfs(current: JsonValue) -> None:
        if isinstance(current, dict):
            for key, value in current.items():
                if _is_metadata_key(key):
                    continue
                if key in targets_set:
                    logger.debug("Found target category: %s", key)
                    excluded = exclude_map.get(key, set())
                    leaves = list(_collect_leaf_device_names(value, excluded_keys=excluded))
                    if value is None:
                        leaves.append(key)
                    collected[key].extend(leaves)
                if isinstance(value, (dict, list)):
                    dfs(value)
        elif isinstance(current, list):
            for item in current:
                dfs(item)

    dfs(node)

    # Deduplicate and sort results
    for category in collected:
        seen: Set[str] = set()
        unique_ordered = [x for x in collected[category] if not (x in seen or seen.add(x))]
        collected[category] = sorted(unique_ordered)

    return collected


def collect_child_devices(
        data: Dict[str, JsonValue],
        target_categories: List[str],
        parent: str = "root",
        depth: int = 0,
        exclude_subtrees: Dict[str, Iterable[str]] | None = None,
) -> Dict[str, List[str]]:
    """Recursively collects leaf device names for specified categories.

    Walks the hierarchy, finds each target category, and collects leaf device names
    in its subtree, ignoring metadata keys and excluded subtrees.

    Args:
        data: The category hierarchy data (dict).
        target_categories: List of category names (e.g., ['iPhone', 'Android Phone']).
        parent: Parent node name for logging context.
        depth: Recursion depth for logging indentation.
        exclude_subtrees: Mapping of target_category -> keys to skip.

    Returns:
        Dictionary mapping each target category to a sorted list of leaf device names.
    """
    indent = "  " * depth
    logger.debug("%sProcessing node: %s (type: %s)", indent, parent, type(data).__name__)

    if not isinstance(data, dict):
        logger.debug("%sSkipping non-dict node: %s", indent, type(data).__name__)
        return {cat: [] for cat in target_categories}

    exclude_map = {k: set(v) for k, v in (exclude_subtrees or {}).items()}
    results = _find_and_collect_for_targets(data, target_categories, exclude_map=exclude_map)
    for category, devices in results.items():
        logger.debug("%sCollected %d devices for %s", indent, len(devices), category)
    return results


def get_child_devices_for_categories(
        client: IFixitAPIClient,
        categories: List[str],
        output_file: str,
        exclude_subtrees: Dict[str, Iterable[str]] | None = None,
) -> None:
    """Fetches and extracts child devices for given categories and writes to a file.

    Args:
        client: The IFixitAPIClient instance.
        categories: List of category names (e.g., ['iPhone', 'Android Phone']).
        output_file: Path to write the results.
        exclude_subtrees: Mapping of target_category -> keys to skip.
    """
    try:
        logger.info("Fetching category hierarchy...")
        data = client.get_category_hierarchy(params={"display": "hierarchy"})
        logger.debug("Category hierarchy fetched successfully")
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404:
            logger.debug("Category hierarchy not found (404), returning empty results")
            data = {}
        else:
            logger.error("Failed to fetch category hierarchy: %s", exc, exc_info=True)
            data = {}

    logger.info("Collecting child devices...")
    child_devices = collect_child_devices(data, categories, exclude_subtrees=exclude_subtrees)

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(child_devices, f, indent=2, ensure_ascii=False)
        logger.info("Child devices written to %s", output_file)
    except Exception as exc:
        logger.error("Failed to write to %s: %s", output_file, exc, exc_info=True)

    for category, devices in child_devices.items():
        print(f"\nChild devices for {category}:")
        if devices:
            print(json.dumps(devices, indent=2, ensure_ascii=False))
        else:
            print(f"No child devices found for {category}")


def _to_ifixit_title(name: str) -> str:
    """Converts a human-readable device name into a baseline iFixit wiki title.

    Args:
        name: Human-readable device name (e.g., 'Samsung Galaxy S22 Ultra').

    Returns:
        A baseline iFixit title format (e.g., 'Samsung_Galaxy_S22_Ultra').
    """
    s = re.sub(r"\s+", "_", name.strip())
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s


def print_device_data(
        client: IFixitAPIClient,
        devices: List[str],
        output_file: Optional[str] = None,
) -> None:
    """Fetches and prints device repairability scores concurrently.

    Uses a thread pool with rate limiting to fetch data for each device.
    Displays a progress bar using tqdm. Non-critical errors (e.g., 404) are
    suppressed from console output. Optionally writes devices with scores to a JSON file.

    Args:
        client: The IFixitAPIClient instance.
        devices: List of human-readable device names.
        output_file: Optional path to write devices with scores as JSON.
            Format: [{"name": str, "title": str, "repairability_score": number, "brand": str, "link": str}, ...]
    """
    # Deduplicate while preserving order
    seen: Set[str] = set()
    unique_devices = [d for d in devices if not (d in seen or seen.add(d))]

    if not unique_devices:
        print("No devices provided.")
        return

    class _RateLimiter:
        """Token-bucket rate limiter for controlling API request rate."""

        def __init__(self, rate_per_sec: int, burst: Optional[int] = None) -> None:
            self.rate = max(1, rate_per_sec)
            self.capacity = burst if burst is not None else self.rate
            self._tokens: float = float(self.capacity)
            self._last: float = perf_counter()
            self._lock = __import__("threading").Lock()

        def acquire(self) -> None:
            """Acquire a token, blocking if necessary."""
            with self._lock:
                now = perf_counter()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens < 1.0:
                    time.sleep((1.0 - self._tokens) / self.rate)
                    self._last = perf_counter()
                    self._tokens = max(0.0, self._tokens + ((1.0 - self._tokens) / self.rate) * self.rate)
                self._tokens -= 1.0

    def _fetch_score(
            device_name: str, max_retries: int = 3, base_backoff: float = 0.75
    ) -> Tuple[str, str, Optional[float], Optional[str], Optional[str], Optional[str]]:
        """Fetches a single device's score with retries.

        Args:
            device_name: Human-readable device name.
            max_retries: Maximum number of retry attempts.
            base_backoff: Base backoff time in seconds for exponential retry.

        Returns:
            Tuple of (device_name, title, score_or_none, brand_or_none, link_or_none, error_message_or_none).
        """
        title = _to_ifixit_title(device_name)
        for attempt in range(max_retries):
            try:
                limiter.acquire()
                data = client.get_category_hierarchy(device_name=title, params=None)
                score = data.get("repairability_score")
                brand = next(
                    (entry.get("value") for entry in data.get("info", []) if entry.get("name") == "Device Brand"),
                    None,
                )
                link = f"https://www.ifixit.com/Device/{title}"
                return device_name, title, score, brand, link, None
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                retry_after = getattr(getattr(exc, "response", None), "headers", {}).get("Retry-After")
                sleep_s = float(retry_after) if retry_after else base_backoff * (2 ** attempt)
                transient = status in {429, 500, 502, 503, 504} or status is None

                if status == 404:
                    return device_name, title, None, None, None, str(exc)

                if attempt < max_retries - 1 and transient:
                    time.sleep(sleep_s)
                    continue

                logger.error(
                    "Failed to fetch repairability score",
                    exc_info=exc,
                    extra={"device": device_name},
                )
                return device_name, title, None, None, None, str(exc)

        return device_name, title, None, None, None, "Max retries exceeded"

    max_workers = 8
    requests_per_second = 4
    limiter = _RateLimiter(rate_per_sec=requests_per_second)

    results: List[Tuple[str, str, Optional[float], Optional[str], Optional[str]]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_fetch_score, name): name for name in unique_devices}
        for fut in tqdm.tqdm(
                as_completed(future_map),
                total=len(future_map),
                desc="Fetching scores",
                unit="device",
                dynamic_ncols=True,
        ):
            results.append(fut.result())

    # Partition and sort results
    with_score = [(n, t, s, b, l) for n, t, s, b, l, err in results if s is not None]
    without_score = [(n, t) for n, t, s, b, l, err in results if s is None]
    with_score.sort(key=lambda x: x[0])

    # Output results
    if without_score:
        print("\nDevices without a repairability score (or failed to fetch):")
        for name, title in sorted(without_score, key=lambda x: x[0]):
            print(f"- {name} ({title})")

    print("\nRepairability scores for devices:")
    for name, title, score, brand, link in with_score:
        print(f"- {name} ({title}): {score}")

    print("\nSummary:")
    print(f"- Devices with a repairability score: {len(with_score)}")
    print(f"- Total devices processed: {len(results)}")

    if output_file:
        try:
            payload = [
                {"name": name, "title": title, "repairability_score": score, "brand": brand, "link": link}
                for name, title, score, brand, link in with_score
            ]
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            print(f"\nWrote {len(payload)} devices with scores to: {output_file}")
        except Exception as exc:
            logger.error("Failed to write results to %s: %s", output_file, exc, exc_info=True)


def main() -> None:
    """Entry point for the script."""
    parser = argparse.ArgumentParser(description="Fetch iFixit device data")
    parser.add_argument("--categories", nargs="+", default=["iPhone", "Android Phone"], help="Categories to fetch")
    parser.add_argument("--output", default="child_devices.json", help="Output file for child devices")
    parser.add_argument("--scores-output", default="devices_with_scores.json", help="Output file for scores")
    args = parser.parse_args()

    client = IFixitAPIClient(log_level=log_level)
    exclude_subtrees = {"iPhone": {"iPhone Accessories"}}
    get_child_devices_for_categories(client, args.categories, args.output, exclude_subtrees)

    try:
        with open(args.output, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error("Output file %s not found", args.output)
        return
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in %s: %s", args.output, exc)
        return

    demo_devices = list(dict.fromkeys(data.get("iPhone", []) + data.get("Android Phone", [])))
    if not demo_devices:
        print("No demo devices found.")
        return

    print_device_data(client, demo_devices, args.scores_output)


if __name__ == "__main__":
    main()
