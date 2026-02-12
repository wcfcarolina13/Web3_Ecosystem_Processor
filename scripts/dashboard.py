#!/usr/bin/env python3
"""
Launch the Ecosystem Research dashboard.

Usage:
    python scripts/dashboard.py --chain near
    python scripts/dashboard.py --chain near --port 5050
    python scripts/dashboard.py --chain near --open
"""

import argparse
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard import create_app


def main():
    parser = argparse.ArgumentParser(description="Launch research dashboard")
    parser.add_argument("--chain", help="Default chain to display (e.g., near)")
    parser.add_argument("--port", type=int, default=5050, help="Port (default: 5050)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--open", action="store_true", help="Open browser automatically")
    args = parser.parse_args()

    app = create_app(default_chain=args.chain)
    url = f"http://{args.host}:{args.port}"
    print(f"\n  Ecosystem Research Dashboard")
    print(f"  {url}\n")
    if args.open:
        webbrowser.open(url)
    app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
