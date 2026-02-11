"""
The Grid API client for ecosystem research.

Usage:
    from lib.grid_client import GridAPIClient, GridEntityMatcher

    client = GridAPIClient()
    results = client.search_all("Aptos")

    matcher = GridEntityMatcher()
    match = matcher.match_by_name("Thala Labs")
"""

from .client import GridAPIClient
from .matcher import GridEntityMatcher
from .models import GridMatch, GridMultiMatch

__all__ = ["GridAPIClient", "GridEntityMatcher", "GridMatch", "GridMultiMatch"]
