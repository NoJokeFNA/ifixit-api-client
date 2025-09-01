import json
import logging
from typing import Dict, Iterable, List, Set, Union

from ifixit_api_client import IFixitAPIClient

# Configure logging
logging.basicConfig(level=logging.DEBUG)
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


def main():
    """Entry point for manual execution."""
    client = IFixitAPIClient(log_level=logging.DEBUG)
    categories = ["iPhone", "Android Phone"]
    exclude_subtrees = {
        "iPhone": {"iPhone Accessories"},
        # Add more exclusions as needed, e.g.:
        # "Android Phone": {"Android Phone Accessories"},
    }
    output_file = "child_devices.json"
    get_child_devices_for_categories(client, categories, output_file, exclude_subtrees=exclude_subtrees)


if __name__ == "__main__":
    main()
