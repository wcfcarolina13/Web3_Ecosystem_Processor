#!/usr/bin/env python3
"""
Grid API Client for Ecosystem Research
Queries The Grid's GraphQL API at https://beta.node.thegrid.id/graphql

Usage:
    python grid_client.py search_products "Aptos" --limit 10
    python grid_client.py search_assets "APT" --limit 5
    python grid_client.py ecosystem "Aptos" --limit 50
    python grid_client.py raw "{ products(limit: 3) { name } }"
"""

import argparse
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

GRID_ENDPOINT = "https://beta.node.thegrid.id/graphql"


def execute_graphql(query: str, variables: dict = None) -> dict:
    """Execute a GraphQL query against The Grid API."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    data = json.dumps(payload).encode('utf-8')
    req = Request(GRID_ENDPOINT, data=data, headers={
        "Content-Type": "application/json",
        "Accept": "application/json"
    })

    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except URLError as e:
        return {"error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def search_products(name: str = None, product_type: str = None, status: str = None, limit: int = 20) -> dict:
    where_clauses = []
    if name:
        if '%' not in name:
            name = f"%{name}%"
        where_clauses.append(f'name: {{ _like: "{name}" }}')
    if product_type:
        if '%' not in product_type:
            product_type = f"%{product_type}%"
        where_clauses.append(f'productType: {{ name: {{ _like: "{product_type}" }} }}')
    if status:
        where_clauses.append(f'productStatus: {{ name: {{ _eq: "{status}" }} }}')

    where_clause = ", ".join(where_clauses)
    where_str = f"where: {{ {where_clause} }}, " if where_clauses else ""

    query = f"""{{
        products({where_str}limit: {limit}) {{
            id
            name
            description
            productType {{ name }}
            productStatus {{ name }}
            root {{ id slug }}
            urls {{ url urlType {{ name }} }}
        }}
    }}"""
    return execute_graphql(query)


def search_assets(name: str = None, asset_type: str = None, status: str = None, limit: int = 20) -> dict:
    where_clauses = []
    if name:
        if '%' not in name:
            name = f"%{name}%"
        where_clauses.append(f'name: {{ _like: "{name}" }}')
    if asset_type:
        if '%' not in asset_type:
            asset_type = f"%{asset_type}%"
        where_clauses.append(f'assetType: {{ name: {{ _like: "{asset_type}" }} }}')
    if status:
        where_clauses.append(f'assetStatus: {{ name: {{ _eq: "{status}" }} }}')

    where_clause = ", ".join(where_clauses)
    where_str = f"where: {{ {where_clause} }}, " if where_clauses else ""

    query = f"""{{
        assets({where_str}limit: {limit}) {{
            id
            name
            ticker
            description
            assetType {{ name }}
            assetStatus {{ name }}
            root {{ id slug }}
            urls {{ url urlType {{ name }} }}
        }}
    }}"""
    return execute_graphql(query)


def get_ecosystem(chain_name: str, limit: int = 50) -> dict:
    products_result = search_products(name=chain_name, limit=limit)
    assets_result = search_assets(name=chain_name, limit=limit)
    return {
        "ecosystem": chain_name,
        "products": products_result.get("data", {}).get("products", []),
        "assets": assets_result.get("data", {}).get("assets", [])
    }


def get_product_types() -> dict:
    return execute_graphql("{ productTypes(limit: 100) { id name } }")


def get_asset_types() -> dict:
    return execute_graphql("{ assetTypes(limit: 100) { id name } }")


def format_output(data: dict, format_type: str = "json") -> str:
    if format_type == "json":
        return json.dumps(data, indent=2)
    elif format_type == "simple":
        output = []
        if "data" in data:
            for key, items in data["data"].items():
                if isinstance(items, list):
                    output.append(f"\n=== {key.upper()} ({len(items)} results) ===\n")
                    for item in items:
                        name = item.get("name", "Unknown")
                        desc = item.get("description", "")[:100] + "..." if item.get("description") else ""
                        item_type = item.get("productType", item.get("assetType", {}))
                        type_name = item_type.get("name", "") if item_type else ""
                        status = item.get("productStatus", item.get("assetStatus", {}))
                        status_name = status.get("name", "") if status else ""
                        ticker = item.get("ticker", "")
                        output.append(f"• {name}" + (f" ({ticker})" if ticker else ""))
                        if type_name:
                            output.append(f"  Type: {type_name}")
                        if status_name:
                            output.append(f"  Status: {status_name}")
                        if desc:
                            output.append(f"  {desc}")
                        output.append("")
        elif "products" in data or "assets" in data:
            if data.get("products"):
                output.append(f"\n=== PRODUCTS ({len(data['products'])} results) ===\n")
                for item in data["products"]:
                    output.append(f"• {item.get('name', 'Unknown')} [{item.get('productType', {}).get('name', '')}]")
            if data.get("assets"):
                output.append(f"\n=== ASSETS ({len(data['assets'])} results) ===\n")
                for item in data["assets"]:
                    ticker = item.get("ticker", "")
                    output.append(f"• {item.get('name', 'Unknown')}" + (f" ({ticker})" if ticker else ""))
        return "\n".join(output)
    return str(data)


def main():
    parser = argparse.ArgumentParser(description="Query The Grid API for ecosystem research")
    parser.add_argument("command", choices=["search_products", "search_assets", "ecosystem", "raw", "product_types", "asset_types"])
    parser.add_argument("query", nargs="?", help="Search query or raw GraphQL")
    parser.add_argument("--type", "-t", help="Filter by type")
    parser.add_argument("--status", "-s", help="Filter by status")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Max results (default: 20)")
    parser.add_argument("--format", "-f", choices=["json", "simple"], default="simple", help="Output format")

    args = parser.parse_args()

    if args.command == "search_products":
        result = search_products(name=args.query, product_type=args.type, status=args.status, limit=args.limit)
    elif args.command == "search_assets":
        result = search_assets(name=args.query, asset_type=args.type, status=args.status, limit=args.limit)
    elif args.command == "ecosystem":
        result = get_ecosystem(args.query, limit=args.limit) if args.query else {"error": "Chain name required"}
    elif args.command == "raw":
        result = execute_graphql(args.query) if args.query else {"error": "Query required"}
    elif args.command == "product_types":
        result = get_product_types()
    elif args.command == "asset_types":
        result = get_asset_types()
    else:
        parser.print_help()
        sys.exit(1)

    print(format_output(result, args.format))


if __name__ == "__main__":
    main()
