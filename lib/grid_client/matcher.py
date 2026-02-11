"""
Entity matcher for matching ecosystem projects to Grid entries.

Simplified from the News-Summarizer's GridEntityMatcher:
- Focused on name-based and URL-based matching (not news headlines)
- Uses confidence scoring to rank results
- Includes caching to avoid redundant API calls
"""

import re
from typing import Dict, List, Optional, Tuple

from .client import GridAPIClient
from .models import GridMatch, GridMultiMatch


class GridEntityMatcher:
    """
    Matches ecosystem projects to Grid subjects (profiles, products, assets, entities).
    """

    def __init__(self, client: Optional[GridAPIClient] = None):
        self.client = client or GridAPIClient()
        self._cache: Dict[str, GridMultiMatch] = {}

    def match_by_name(self, name: str) -> GridMultiMatch:
        """
        Match a project name to Grid subjects.

        Returns GridMultiMatch with all matches above confidence threshold,
        sorted by confidence (highest first).
        """
        cache_key = f"name:{name.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not name or len(name) < 2:
            result = GridMultiMatch(matched=False)
            self._cache[cache_key] = result
            return result

        # Search across all Grid types
        results = self.client.search_all(name)

        all_candidates: List[Tuple[GridMatch, float]] = []
        seen_names: set = set()

        # Score profile matches
        for profile in results.get("profiles", []):
            match = self._match_from_profile(profile)
            if match.name.lower() not in seen_names:
                score = self._score_match(match.name, name)
                if score >= 0.6:
                    match.confidence = score
                    all_candidates.append((match, score))
                    seen_names.add(match.name.lower())

        # Score product matches
        for product in results.get("products", []):
            match = self._match_from_product(product)
            if match.name.lower() not in seen_names:
                score = self._score_match(match.name, name)
                if score >= 0.6:
                    match.confidence = score
                    all_candidates.append((match, score))
                    seen_names.add(match.name.lower())

        # Score asset matches
        for asset in results.get("assets", []):
            match = self._match_from_asset(asset)
            if match.name.lower() not in seen_names:
                score = self._score_match(match.name, name)
                if score >= 0.6:
                    match.confidence = score
                    all_candidates.append((match, score))
                    seen_names.add(match.name.lower())

        # Score entity matches
        for entity in results.get("entities", []):
            match = self._match_from_entity(entity)
            if match.name.lower() not in seen_names:
                score = self._score_match(match.name, name)
                if score >= 0.6:
                    match.confidence = score
                    all_candidates.append((match, score))
                    seen_names.add(match.name.lower())

        if not all_candidates:
            result = GridMultiMatch(matched=False)
            self._cache[cache_key] = result
            return result

        # Sort by confidence (highest first)
        all_candidates.sort(key=lambda x: x[1], reverse=True)
        matches = [match for match, _ in all_candidates]

        result = GridMultiMatch(matched=True, matches=matches)
        self._cache[cache_key] = result
        return result

    def match_by_url(self, url: str) -> GridMultiMatch:
        """
        Match a URL to Grid subjects.

        Returns GridMultiMatch with entries whose urlMain matches the given URL.
        """
        cache_key = f"url:{url.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not url:
            result = GridMultiMatch(matched=False)
            self._cache[cache_key] = result
            return result

        roots = self.client.search_by_url(url)

        matches = []
        for root in roots:
            # Extract profiles from root
            for profile in root.get("profileInfos", []):
                matches.append(
                    GridMatch(
                        matched=True,
                        grid_type="profile",
                        grid_id=profile.get("id", ""),
                        name=profile.get("name", ""),
                        category=profile.get("profileType", {}).get("name", "")
                        if profile.get("profileType")
                        else "",
                        confidence=1.0,
                        url=root.get("urlMain", ""),
                    )
                )
            # Extract products from root
            for product in root.get("products", []):
                matches.append(
                    GridMatch(
                        matched=True,
                        grid_type="product",
                        grid_id=product.get("id", ""),
                        name=product.get("name", ""),
                        category=product.get("productType", {}).get("name", "")
                        if product.get("productType")
                        else "",
                        confidence=1.0,
                        url=root.get("urlMain", ""),
                    )
                )

        if not matches:
            result = GridMultiMatch(matched=False)
        else:
            result = GridMultiMatch(matched=True, matches=matches)

        self._cache[cache_key] = result
        return result

    def _score_match(self, entity_name: str, search_name: str) -> float:
        """
        Score how well an entity matches the search name.
        Higher score = better match. Range: 0.0 to 2.0.
        """
        if not entity_name:
            return 0.0

        entity_lower = entity_name.lower().strip()
        search_lower = search_name.lower().strip()

        score = 0.0

        # Legal/noise suffixes that indicate a different entity
        noise_suffixes = [
            " s.l.", " ltd", " ltd.", " gmbh", " inc", " inc.",
            " corp", " corp.", " llc", " plc", " pte",
            " slugs", " gang", " punks", " apes", " club",
        ]

        has_noise = any(
            suffix in entity_lower and suffix not in search_lower
            for suffix in noise_suffixes
        )

        # Exact match
        if entity_lower == search_lower:
            score += 1.0
        # Entity starts with search name
        elif entity_lower.startswith(search_lower + " ") or entity_lower.startswith(
            search_lower + "-"
        ):
            score += 0.75 if not has_noise else 0.4
        elif entity_lower.startswith(search_lower):
            score += 0.7 if not has_noise else 0.3
        # Search name contained in entity
        elif search_lower in entity_lower:
            entity_words = set(entity_lower.split())
            search_words = set(search_lower.split())
            extra = entity_words - search_words - {"the", "a", "an", "of", "and", "for"}
            if len(extra) > 1:
                score += 0.3
            elif has_noise:
                score += 0.3
            else:
                score += 0.5
        # Entity name contained in search
        elif entity_lower in search_lower:
            score += 0.5

        # Bonus: exact word boundary match
        if re.search(r"\b" + re.escape(entity_lower) + r"\b", search_lower):
            score += 0.6
        elif entity_lower in search_lower:
            score += 0.3

        # Penalty for noise suffixes
        if has_noise and entity_lower != search_lower:
            score -= 0.3

        return max(0.0, min(score, 2.0))

    # ── Match Factory Methods ─────────────────────────────────────

    def _match_from_profile(self, profile: Dict) -> GridMatch:
        root = profile.get("root", {}) or {}
        return GridMatch(
            matched=True,
            grid_type="profile",
            grid_id=profile.get("id", ""),
            name=profile.get("name", ""),
            description=profile.get("descriptionShort", ""),
            category=profile.get("profileType", {}).get("name", "")
            if profile.get("profileType")
            else "",
            url=root.get("urlMain", ""),
        )

    def _match_from_product(self, product: Dict) -> GridMatch:
        root = product.get("root", {}) or {}
        return GridMatch(
            matched=True,
            grid_type="product",
            grid_id=product.get("id", ""),
            name=product.get("name", ""),
            description=product.get("description", ""),
            category=product.get("productType", {}).get("name", "")
            if product.get("productType")
            else "",
            url=root.get("urlMain", ""),
        )

    def _match_from_asset(self, asset: Dict) -> GridMatch:
        root = asset.get("root", {}) or {}
        return GridMatch(
            matched=True,
            grid_type="asset",
            grid_id=asset.get("id", ""),
            name=asset.get("name", ""),
            ticker=asset.get("ticker", ""),
            category="Token",
            url=root.get("urlMain", ""),
        )

    def _match_from_entity(self, entity: Dict) -> GridMatch:
        entity_type = entity.get("entityType", {})
        country = entity.get("country", {})
        return GridMatch(
            matched=True,
            grid_type="entity",
            grid_id=entity.get("id", ""),
            name=entity.get("name", ""),
            entity_type_name=entity_type.get("name", "") if entity_type else "",
            country=country.get("name", "") if country else "",
        )
