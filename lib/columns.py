"""
Column definitions for Ecosystem Research CSVs.
Single source of truth for column names and order.
"""

CORRECT_COLUMNS = [
    "Name",
    "Suspect USDT support?",
    "Skip",
    "Added",
    "Web3 but no stablecoin",
    "General Stablecoin Adoption",
    "To be Added",
    "Processed?",
    "In Admin",
    "TG/TON appstore (no main URL)",
    "Final Status",
    "Notes",
    "Source",
    "Category",
    "Category Rank",
    "Original URL",
    "Best URL",
    "Status",
    "Matched URL",
    "Profile Name",
    "Slug",
    "Root ID",
    "Telegram Channels",
    "Secondary URL",
    "AI Research",
    "AI Notes & Sources",
    "Chain",
    "USDT Support",
    "USDT Type",
    "Starknet Support",
    "Starknet Type",
    "Solana Support",
    "Solana Type",
    "AI Evidence URLs",
]


def empty_row(chain: str = "") -> dict:
    """Return an empty row dict with all columns initialized to ''."""
    row = {col: "" for col in CORRECT_COLUMNS}
    if chain:
        row["Chain"] = chain
    return row
