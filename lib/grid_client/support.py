"""
Asset support detection utilities for Grid API data.

Extracts and checks product→asset relationships from Grid root data.
Shared by grid_match.py and enrich_grid_assets.py.
"""

from typing import Dict, List, Set


# Map our target asset tickers to Grid asset tickers/names
# Grid uses "USDt" not "USDT", and full names like "Solana" not "SOL"
TARGET_ASSET_GRID_MAP = {
    "USDT": {"USDt", "USDT", "Tether USDt", "Tether"},
    "USDC": {"USDC", "USD Coin"},
    "SOL": {"SOL", "Solana"},
    "STRK": {"STRK", "Starknet"},
    "ADA": {"ADA", "Cardano"},
}


def extract_supported_tickers(root_data: dict) -> Set[str]:
    """
    Extract all asset tickers that are 'Supported by' any product under this root.
    """
    tickers = set()
    for product in root_data.get("products", []):
        for rel in product.get("productAssetRelationships", []):
            support_type = rel.get("assetSupportType") or {}
            if support_type.get("slug") == "supported_by":
                asset = rel.get("asset", {})
                ticker = asset.get("ticker", "")
                name = asset.get("name", "")
                if ticker:
                    tickers.add(ticker)
                if name:
                    tickers.add(name)
    return tickers


def check_target_support(
    supported_tickers: Set[str], target_assets: List[str]
) -> Dict[str, bool]:
    """
    Check which target assets are supported based on Grid tickers.
    Returns {asset: True/False}.
    """
    result = {}
    for asset in target_assets:
        grid_aliases = TARGET_ASSET_GRID_MAP.get(asset, {asset})
        found = bool(grid_aliases & supported_tickers)
        result[asset] = found
    return result
