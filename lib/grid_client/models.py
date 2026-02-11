"""
Data models for Grid API results.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class GridMatch:
    """
    Represents a single match from The Grid API.

    Grid types:
    - profile: The project/brand (e.g., "Solana" the project)
    - product: Things built by profiles (e.g., "Phantom Wallet")
    - asset: Tokens/coins (e.g., "SOL" token)
    - entity: Legal structures (e.g., "Solana Foundation")
    """

    matched: bool = False
    grid_type: str = ""  # profile, product, asset, entity
    grid_id: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    confidence: float = 0.0
    # Type-specific fields
    ticker: str = ""  # For assets
    entity_type_name: str = ""  # For entities
    country: str = ""  # For entities
    url: str = ""  # Main URL if available

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "grid_type": self.grid_type,
            "grid_id": self.grid_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "confidence": round(self.confidence, 2),
            "ticker": self.ticker,
            "url": self.url,
        }


@dataclass
class GridMultiMatch:
    """
    Represents multiple matches from The Grid API for a single query.
    """

    matched: bool = False
    matches: List[GridMatch] = field(default_factory=list)

    @property
    def primary(self) -> Optional[GridMatch]:
        """Get the highest-confidence match."""
        return self.matches[0] if self.matches else None

    @property
    def profiles(self) -> List[GridMatch]:
        return [m for m in self.matches if m.grid_type == "profile"]

    @property
    def products(self) -> List[GridMatch]:
        return [m for m in self.matches if m.grid_type == "product"]

    @property
    def assets(self) -> List[GridMatch]:
        return [m for m in self.matches if m.grid_type == "asset"]

    @property
    def entities(self) -> List[GridMatch]:
        return [m for m in self.matches if m.grid_type == "entity"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "match_count": len(self.matches),
            "subjects": ", ".join(m.name for m in self.matches),
            "matches": [m.to_dict() for m in self.matches],
        }
