"""
Column definitions for Ecosystem Research CSVs.
Single source of truth for column names and order.
Aligned with the team's standard column format.
"""

CORRECT_COLUMNS = [
    "Project Name",
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
    "Website",
    "X Link",
    "X Handle",
    "Telegram",
    "Category",
    "Release Date",
    "Product Status",
    "The Grid Status",
    "Profile Name",
    "Root ID",
    "Matched URL",
    "Matched via",
    "Chain",
    "Source",
    "Notes",
    "Evidence URLs",
]


def empty_row(chain: str = "") -> dict:
    """Return an empty row dict with all columns initialized to ''."""
    row = {col: "" for col in CORRECT_COLUMNS}
    if chain:
        row["Chain"] = chain
    return row
