import json
import logging
import sys
from typing import Dict, Iterable, List, Set, Union

from ifixit_api_client import IFixitAPIClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JsonValue = Union[None, Dict[str, "JsonValue"], List["JsonValue"], str, int, float, bool]


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


def _collect_leaf_device_names(node: JsonValue, excluded_keys: Set[str] | None = None) -> List[str]:
    """Collects all leaf device names under a node.

    A leaf device is represented by:
      - a dict entry with value None: {"Asus ROG Phone 6": None}
      - a string inside a list, e.g., {"Some Series": ["Model A", "Model B"]}
      - nested dicts are traversed recursively

    Args:
        node: The current JSON-like node (dict, list, None, etc.).
        excluded_keys: A set of keys (category names) to exclude entirely (skip subtree).

    Returns:
        A list of leaf device names (strings).
    """
    leaves: List[str] = []
    excluded_keys = excluded_keys or set()

    if isinstance(node, dict):
        for key, value in node.items():
            if _is_metadata_key(key) or key in excluded_keys:
                # Skip metadata or explicitly excluded subtrees
                continue
            if value is None:
                # Leaf represented by key -> None
                leaves.append(key)
            elif isinstance(value, dict):
                leaves.extend(_collect_leaf_device_names(value, excluded_keys))
            elif isinstance(value, list):
                # Traverse list items
                for item in value:
                    if isinstance(item, dict):
                        leaves.extend(_collect_leaf_device_names(item, excluded_keys))
                    elif isinstance(item, str):
                        # Strings in lists are treated as leaf device names
                        leaves.append(item)
                    elif item is None:
                        # Rare but supported: list item that is None implies the key is a leaf
                        leaves.append(key)
            else:
                # Scalars other than None are not expected here, ignore safely
                continue

    elif isinstance(node, list):
        for item in node:
            leaves.extend(_collect_leaf_device_names(item, excluded_keys))

    # Other scalar types (str, int, float, bool, None) at this level do not carry key names
    return leaves


def _find_and_collect_for_targets(
        node: JsonValue, target_categories: Iterable[str], exclude_map: Dict[str, Set[str]] | None = None
) -> Dict[str, List[str]]:
    """Finds each target category in the tree and collects all leaf devices under it.

    This scans the entire structure. When a key matches a target category, all
    descendant leaves beneath that key are collected.

    Args:
        node: The root node of the hierarchy.
        target_categories: An iterable of category names to search for.
        exclude_map: Optional mapping target_category -> set of subtree keys to exclude.

    Returns:
        A dictionary mapping target category -> list of leaf device names.
    """
    targets_set: Set[str] = set(target_categories)
    collected: Dict[str, List[str]] = {t: [] for t in targets_set}
    exclude_map = exclude_map or {}

    def dfs(current: JsonValue):
        if isinstance(current, dict):
            for key, value in current.items():
                if _is_metadata_key(key):
                    continue

                # If we encounter a target category key
                if key in targets_set:
                    logger.debug("Found target category: %s", key)
                    # Collect leaves directly under this subtree with category-specific exclusions
                    excluded = exclude_map.get(key, set())
                    leaves = _collect_leaf_device_names(value, excluded_keys=excluded)
                    # Also include the key itself if it is a leaf (value is None)
                    if value is None:
                        leaves.append(key)
                    collected[key].extend(leaves)

                # Continue traversal to find deeper matches
                if isinstance(value, (dict, list)):
                    dfs(value)

        elif isinstance(current, list):
            for item in current:
                dfs(item)

    dfs(node)

    # Deduplicate and sort results
    for k in collected:
        # Preserve insertion order while removing duplicates
        seen: Set[str] = set()
        unique_ordered = [x for x in collected[k] if not (x in seen or seen.add(x))]
        collected[k] = sorted(unique_ordered)

    return collected


def collect_child_devices(
        data: Dict[str, JsonValue],
        target_categories: List[str],
        parent: str = "root",
        depth: int = 0,
        exclude_subtrees: Dict[str, Iterable[str]] | None = None,
) -> Dict[str, List[str]]:
    """Recursively collect all leaf device names for specified categories.

    This function walks the entire hierarchy. For each target category name,
    it finds every occurrence of that category key and collects all leaf device
    names in its subtree (i.e., the deepest nodes where value is None or strings
    inside lists). Metadata keys are ignored.

    Args:
        data: The category hierarchy data (dict).
        target_categories: List of category names (e.g., ['iPhone', 'Android Phone']).
        parent: Parent node name used only for logging context.
        depth: Current recursion depth used only for logging indentation.
        exclude_subtrees: Mapping of target_category -> iterable of subtree keys to skip
            entirely (e.g., {'iPhone': ['iPhone Accessories']}).


    Returns:
        A dictionary mapping each target category to a sorted list of leaf device names.
    """
    indent = "  " * depth
    logger.debug("%sProcessing root node: %s (type: %s)", indent, parent, type(data).__name__)

    if not isinstance(data, dict):
        logger.debug("%sSkipping non-dict root: %s", indent, type(data).__name__)
        return {cat: [] for cat in target_categories}

    # Normalize exclude map to sets
    exclude_map: Dict[str, Set[str]] = {
        k: set(v) for k, v in (exclude_subtrees or {}).items()
    }

    results = _find_and_collect_for_targets(data, target_categories, exclude_map=exclude_map)
    for category, devices in results.items():
        logger.debug("%sCollected %d devices for %s", indent, len(devices), category)
    return results


def get_child_devices_for_categories(
        client: IFixitAPIClient, categories: List[str], output_file: str,
        exclude_subtrees: Dict[str, Iterable[str]] | None = None
) -> None:
    """Fetch and extract all child devices for the given categories and write to a file.

    Args:
        client: The IFixitAPIClient instance.
        categories: List of category names (e.g., ['iPhone', 'Android Phone']).
        output_file: Path to the output file to write the results.
        exclude_subtrees: Mapping of target_category -> iterable of subtree keys to skip.
    """
    try:
        logger.info("Fetching category hierarchy...")
        data = client.get_category_hierarchy(params={"display": "hierarchy"})
        logger.debug("Full category hierarchy fetched.")

        logger.info("Collecting child devices...")
        child_devices = collect_child_devices(data, categories, exclude_subtrees=exclude_subtrees)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(child_devices, f, indent=2, ensure_ascii=False)
        logger.info("Child devices written to %s", output_file)

        # Print results to console for verification
        for category, devices in child_devices.items():
            print(f"\nChild devices for {category}:")
            if devices:
                print(json.dumps(devices, indent=2, ensure_ascii=False))
            else:
                print(f"No child devices found for {category}")

    except Exception as e:
        logger.error("Failed to fetch or process child devices: %s", str(e))
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({category: [] for category in categories}, f, indent=2, ensure_ascii=False)
        logger.info("Empty device lists written to %s due to error", output_file)


def _to_ifixit_title(name: str) -> str:
    """Converts a human-readable device name into a baseline iFixit wiki title.

    This is a baseline conversion; certain models (e.g., 'Plus') may require
    special handling (see _candidate_titles_for_device).

    Args:
        name: Human-readable device name (e.g., 'Samsung Galaxy S22 Ultra').

    Returns:
        A baseline iFixit title format (e.g., 'Samsung_Galaxy_S22_Ultra').
    """
    import re

    s = re.sub(r"\s+", "_", name.strip())
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s


def print_repairability_scores(client: IFixitAPIClient, devices: List[str], output_file: str | None = None) -> None:
    """Fetches and prints the repairability_score for each device, concurrently.

    Uses a simple thread pool with a lightweight token-bucket style rate limiter
    and retry with backoff to avoid hitting rate limits. Displays a progress bar.
    Optionally writes all devices that have a score to a JSON file.

    Args:
        client: The IFixitAPIClient instance.
        devices: List of human-readable device names.
        output_file: Optional path to write devices with scores as JSON.
            The JSON schema is a list of objects:
            [{"name": str, "title": str, "repairability_score": number}, ...]
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from typing import Optional, Tuple

    class _RateLimiter:
        """Simple token-bucket-like limiter for N requests per second."""

        def __init__(self, rate_per_sec: int, burst: int | None = None) -> None:
            self.rate = max(1, rate_per_sec)
            self.capacity = burst if burst is not None else self.rate
            self._tokens = float(self.capacity)
            self._last = time.perf_counter()
            self._lock = __import__("threading").Lock()

        def acquire(self) -> None:
            with self._lock:
                now = time.perf_counter()
                elapsed = now - self._last
                self._last = now
                # Refill tokens
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens < 1.0:
                    # Need to wait for next token
                    needed = (1.0 - self._tokens) / self.rate
                    time.sleep(needed)
                    # After sleeping, assume exactly 1 token available
                    self._last = time.perf_counter()
                    self._tokens = max(0.0, self._tokens + needed * self.rate)
                # Consume one token
                self._tokens -= 1.0

    def _fetch_score(device_name: str,
                     max_retries: int = 3,
                     base_backoff: float = 0.75) -> Tuple[str, str, Optional[float], Optional[str]]:
        """Worker to fetch a single device's score with retries.

        Returns:
            (device_name, title, score_or_none, error_message_or_none)
        """
        title = _to_ifixit_title(device_name)
        for attempt in range(max_retries):
            try:
                limiter.acquire()
                data = client.get_category_hierarchy(device_name=title, params=None)
                score = data.get("repairability_score")
                return device_name, title, score, None
            except Exception as exc:
                # Try to read HTTP status if available
                status = None
                retry_after = None
                resp = getattr(exc, "response", None)
                if resp is not None:
                    try:
                        status = getattr(resp, "status_code", None)
                        retry_after = resp.headers.get("Retry-After")
                    except Exception:
                        pass

                # Respect Retry-After when present
                if retry_after:
                    try:
                        sleep_s = float(retry_after)
                    except ValueError:
                        sleep_s = base_backoff * (2 ** attempt)
                else:
                    sleep_s = base_backoff * (2 ** attempt)

                transient = status in {429, 500, 502, 503, 504} or status is None
                if attempt < max_retries - 1 and transient:
                    time.sleep(sleep_s)
                    continue

                logger.error("Failed to fetch repairability score for %s: %s", device_name, str(exc))
                return device_name, title, None, str(exc)

        return device_name, title, None, "Unknown error"

    # De-duplicate while preserving order
    seen: Set[str] = set()
    unique_devices = [d for d in devices if not (d in seen or seen.add(d))]

    if not unique_devices:
        print("No devices provided.")
        return

    # Progress bar helper
    def _render_progress(done: int, total: int, width: int = 30) -> str:
        ratio = 0 if total == 0 else done / total
        filled = int(round(width * ratio))
        bar = "#" * filled + "-" * (width - filled)
        percent = int(ratio * 100)
        return f"[{bar}] {done}/{total} ({percent}%)"

    def _print_progress(done: int, total: int, is_tty: bool, every_n: int = 0) -> None:
        """Print progress either in-place (TTY) or periodically on new lines (non-TTY)."""
        if is_tty:
            # \x1b[K clears the line to the right of the cursor for clean updates
            sys.stdout.write("\r" + _render_progress(done, total) + "\x1b[K")
            sys.stdout.flush()
        else:
            # Fallback: print every N updates on a new line
            if every_n <= 1 or done == 0 or done == total or (done % every_n == 0):
                percent = 0 if total == 0 else int(done * 100 / total)
                print(f"Progress: {done}/{total} ({percent}%)")

    # Tune these values to your API allowance
    max_workers = 8
    requests_per_second = 4
    limiter = _RateLimiter(rate_per_sec=requests_per_second)

    print("\nRepairability scores for demo devices:")
    total = len(unique_devices)
    done = 0
    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    # For non-TTY, print roughly 20 updates
    step_n = max(1, total // 20)
    _print_progress(done, total, is_tty=is_tty, every_n=step_n)

    results: List[Tuple[str, str, Optional[float], Optional[str]]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_fetch_score, name): name for name in unique_devices}
        for fut in as_completed(future_map):
            results.append(fut.result())
            done += 1
            _print_progress(done, total, is_tty=is_tty, every_n=step_n)

    # Finalize progress line (ensure newline after last update)
    if is_tty:
        sys.stdout.write("\n")
        sys.stdout.flush()

    # Partition results
    with_score = [(n, t, s) for n, t, s, err in results if s is not None]
    without_score = [(n, t) for n, t, s, err in results if s is None]

    # Sort devices with score by name for stable output
    with_score.sort(key=lambda x: x[0])

    # Output
    if without_score:
        print("\nDevices without a repairability score (or failed to fetch):")
        for name, title in sorted(without_score, key=lambda x: x[0]):
            print(f"- {name} ({title})")

    print("\nRepairability scores for demo devices:")
    for name, title, score in with_score:
        print(f"- {name} ({title}): {score}")

    print("\nSummary:")
    print(f"- Devices with a repairability score: {len(with_score)}")
    print(f"- Total devices processed: {len(results)}")

    # Optionally write JSON with all devices that have a score
    if output_file:
        try:
            payload = [
                {"name": name, "title": title, "repairability_score": score}
                for name, title, score in with_score
            ]
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            print(f"\nWrote {len(payload)} devices with a repairability score to: {output_file}")
        except Exception as exc:
            logger.error("Failed to write results to %s: %s", output_file, exc)


def main():
    """Entry point for manual execution."""
    client = IFixitAPIClient(log_level=logging.INFO)
    categories = ["iPhone", "Android Phone"]
    exclude_subtrees = {
        "iPhone": {"iPhone Accessories"},
        # Add more exclusions as needed, e.g.:
        # "Android Phone": {"Android Phone Accessories"},
    }
    output_file = "child_devices.json"
    get_child_devices_for_categories(client, categories, output_file, exclude_subtrees=exclude_subtrees)

    # Go through the output file and execute the method below for both parent nodes
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error("Output file %s not found.", output_file)
        return
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in %s: %s", output_file, e)
        return

    demo_devices = list(dict.fromkeys(data.get("iPhone", []) + data.get("Android Phone", [])))
    if not demo_devices:
        print("No demo devices found.")
        return

    # Write all devices with score to this file
    scores_output_file = "devices_with_scores.json"
    print_repairability_scores(client, demo_devices, output_file=scores_output_file)


if __name__ == "__main__":
    main()
