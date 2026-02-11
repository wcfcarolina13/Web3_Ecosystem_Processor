"""
Read-only client for The Grid's GraphQL API.

Endpoint: https://beta.node.thegrid.id/graphql
No authentication required for public queries.
"""

import json
import time
import logging
from typing import Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .queries import (
    SEARCH_PROFILES_QUERY,
    SEARCH_PRODUCTS_QUERY,
    SEARCH_ASSETS_QUERY,
    SEARCH_ENTITIES_QUERY,
    GET_PROFILE_DETAILS_QUERY,
    SEARCH_BY_URL_QUERY,
    GET_PRODUCT_TYPES_QUERY,
    GET_ASSET_TYPES_QUERY,
    INTROSPECTION_QUERY,
)

logger = logging.getLogger(__name__)

GRID_ENDPOINT = "https://beta.node.thegrid.id/graphql"


class GridAPIClient:
    """
    Read-only client for The Grid's GraphQL API.

    Uses urllib (no external dependencies). Includes retry logic
    with exponential backoff for transient failures.
    """

    def __init__(
        self,
        endpoint: str = GRID_ENDPOINT,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max_retries

    def _execute_query(
        self, query: str, variables: Optional[Dict] = None
    ) -> Dict:
        """Execute a GraphQL query with retry logic."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        data = json.dumps(payload).encode("utf-8")

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                req = Request(
                    self.endpoint,
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                with urlopen(req, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))

                if "errors" in result:
                    logger.warning("GraphQL errors: %s", result["errors"])
                    return {}

                return result.get("data", {})

            except HTTPError as e:
                last_error = e
                if e.code == 429 or e.code >= 500:
                    # Retry on rate limit or server error
                    wait = min(2**attempt, 10)
                    logger.warning(
                        "HTTP %d on attempt %d/%d, retrying in %ds",
                        e.code, attempt, self.max_retries, wait,
                    )
                    time.sleep(wait)
                    continue
                else:
                    logger.error("HTTP %d: %s", e.code, e.reason)
                    return {}

            except (URLError, TimeoutError) as e:
                last_error = e
                wait = min(2**attempt, 10)
                logger.warning(
                    "Network error on attempt %d/%d: %s, retrying in %ds",
                    attempt, self.max_retries, e, wait,
                )
                time.sleep(wait)
                continue

            except Exception as e:
                logger.error("Unexpected error: %s", e)
                return {}

        logger.error("All %d attempts failed. Last error: %s", self.max_retries, last_error)
        return {}

    # ── Search Methods ────────────────────────────────────────────

    def search_profiles(self, term: str, limit: int = 10) -> List[Dict]:
        """Search for profiles (projects/brands) matching the term."""
        data = self._execute_query(
            SEARCH_PROFILES_QUERY, {"search": term, "limit": limit}
        )
        return data.get("profileInfos", [])

    def search_products(self, term: str, limit: int = 10) -> List[Dict]:
        """Search for products matching the term."""
        data = self._execute_query(
            SEARCH_PRODUCTS_QUERY, {"search": term, "limit": limit}
        )
        return data.get("products", [])

    def search_assets(self, term: str, limit: int = 10) -> List[Dict]:
        """Search for assets (tokens) matching the term."""
        data = self._execute_query(
            SEARCH_ASSETS_QUERY, {"search": term, "limit": limit}
        )
        return data.get("assets", [])

    def search_entities(self, term: str, limit: int = 10) -> List[Dict]:
        """Search for entities (legal structures)."""
        data = self._execute_query(
            SEARCH_ENTITIES_QUERY, {"search": term, "limit": limit}
        )
        return data.get("entities", [])

    def search_all(self, term: str, limit: int = 10) -> Dict[str, List[Dict]]:
        """Search across all Grid types at once."""
        return {
            "profiles": self.search_profiles(term, limit),
            "products": self.search_products(term, limit),
            "assets": self.search_assets(term, limit),
            "entities": self.search_entities(term, limit),
        }

    # ── Lookup Methods ────────────────────────────────────────────

    def search_by_url(self, url: str) -> List[Dict]:
        """
        Find Grid entries by URL.
        Useful for matching scraped projects to Grid by their website.
        """
        # Strip protocol and www for broader matching
        clean_url = url.replace("https://", "").replace("http://", "").replace("www.", "")
        # Remove trailing slash
        clean_url = clean_url.rstrip("/")

        data = self._execute_query(SEARCH_BY_URL_QUERY, {"url": clean_url})
        return data.get("roots", [])

    def get_profile_details(self, name: str) -> Dict:
        """Get detailed profile info by exact name match."""
        data = self._execute_query(GET_PROFILE_DETAILS_QUERY, {"name": name})
        profiles = data.get("profileInfos", [])
        return profiles[0] if profiles else {}

    # ── Reference Data ────────────────────────────────────────────

    def get_product_types(self) -> List[Dict]:
        """List all product types in The Grid."""
        data = self._execute_query(GET_PRODUCT_TYPES_QUERY)
        return data.get("productTypes", [])

    def get_asset_types(self) -> List[Dict]:
        """List all asset types in The Grid."""
        data = self._execute_query(GET_ASSET_TYPES_QUERY)
        return data.get("assetTypes", [])

    def get_schema(self) -> Dict:
        """Get the GraphQL schema via introspection."""
        return self._execute_query(INTROSPECTION_QUERY)

    # ── Raw Query ─────────────────────────────────────────────────

    def raw_query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute a raw GraphQL query."""
        return self._execute_query(query, variables)
