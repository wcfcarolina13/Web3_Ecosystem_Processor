#!/usr/bin/env python3
"""
CLI entry point for The Grid API client.

Usage:
    python -m lib.grid_client search "Aptos"
    python -m lib.grid_client search_profiles "Aptos" --limit 5
    python -m lib.grid_client search_products "Aptos" --limit 10
    python -m lib.grid_client search_assets "APT" --limit 5
    python -m lib.grid_client match-url "https://thalalabs.xyz"
    python -m lib.grid_client types
    python -m lib.grid_client raw "{ products(limit: 3) { name } }"
"""

import argparse
import json
import sys

from .client import GridAPIClient


def format_results(data, format_type="simple"):
    """Format API results for display."""
    if format_type == "json":
        return json.dumps(data, indent=2)

    output = []

    if isinstance(data, dict):
        for key, items in data.items():
            if isinstance(items, list):
                output.append(f"\n=== {key.upper()} ({len(items)} results) ===\n")
                for item in items:
                    name = item.get("name", item.get("ticker", "Unknown"))
                    item_id = item.get("id", "")
                    desc = item.get("description", item.get("descriptionShort", ""))
                    if desc and len(desc) > 100:
                        desc = desc[:100] + "..."

                    item_type = (
                        item.get("productType", {}).get("name", "")
                        or item.get("profileType", {}).get("name", "")
                        or item.get("assetType", {}).get("name", "")
                        or item.get("entityType", {}).get("name", "")
                    )
                    if isinstance(item_type, dict):
                        item_type = item_type.get("name", "")

                    ticker = item.get("ticker", "")
                    root = item.get("root", {}) or {}
                    url = root.get("urlMain", "")

                    line = f"  - {name}"
                    if ticker:
                        line += f" ({ticker})"
                    if item_type:
                        line += f" [{item_type}]"
                    output.append(line)

                    if url:
                        output.append(f"    URL: {url}")
                    if desc:
                        output.append(f"    {desc}")
                    if item_id:
                        output.append(f"    ID: {item_id}")
                    output.append("")

    elif isinstance(data, list):
        output.append(f"\n({len(data)} results)\n")
        for item in data:
            name = item.get("name", "Unknown")
            item_id = item.get("id", "")
            output.append(f"  - {name} (ID: {item_id})")

    return "\n".join(output) if output else str(data)


def main():
    parser = argparse.ArgumentParser(
        description="Query The Grid API for ecosystem research"
    )
    parser.add_argument(
        "command",
        choices=[
            "search",
            "search_profiles",
            "search_products",
            "search_assets",
            "search_entities",
            "match-url",
            "profile",
            "types",
            "raw",
            "schema",
        ],
        help="Command to run",
    )
    parser.add_argument("query", nargs="?", help="Search query or raw GraphQL")
    parser.add_argument(
        "--limit", "-l", type=int, default=10, help="Max results (default: 10)"
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "simple"],
        default="simple",
        help="Output format",
    )

    args = parser.parse_args()
    client = GridAPIClient()

    if args.command == "search":
        if not args.query:
            print("Error: search requires a query term")
            sys.exit(1)
        print(f"\nSearching all types for: {args.query}\n")
        result = client.search_all(args.query, limit=args.limit)

    elif args.command == "search_profiles":
        if not args.query:
            print("Error: search_profiles requires a query term")
            sys.exit(1)
        result = {"profiles": client.search_profiles(args.query, limit=args.limit)}

    elif args.command == "search_products":
        if not args.query:
            print("Error: search_products requires a query term")
            sys.exit(1)
        result = {"products": client.search_products(args.query, limit=args.limit)}

    elif args.command == "search_assets":
        if not args.query:
            print("Error: search_assets requires a query term")
            sys.exit(1)
        result = {"assets": client.search_assets(args.query, limit=args.limit)}

    elif args.command == "search_entities":
        if not args.query:
            print("Error: search_entities requires a query term")
            sys.exit(1)
        result = {"entities": client.search_entities(args.query, limit=args.limit)}

    elif args.command == "match-url":
        if not args.query:
            print("Error: match-url requires a URL")
            sys.exit(1)
        print(f"\nMatching URL: {args.query}\n")
        result = {"roots": client.search_by_url(args.query)}

    elif args.command == "profile":
        if not args.query:
            print("Error: profile requires an exact name")
            sys.exit(1)
        result = {"profile_details": [client.get_profile_details(args.query)]}

    elif args.command == "types":
        product_types = client.get_product_types()
        asset_types = client.get_asset_types()
        result = {"product_types": product_types, "asset_types": asset_types}

    elif args.command == "raw":
        if not args.query:
            print("Error: raw requires a GraphQL query string")
            sys.exit(1)
        result = client.raw_query(args.query)

    elif args.command == "schema":
        result = client.get_schema()
        args.format = "json"  # Schema is always JSON

    else:
        parser.print_help()
        sys.exit(1)

    print(format_results(result, args.format))


if __name__ == "__main__":
    main()
