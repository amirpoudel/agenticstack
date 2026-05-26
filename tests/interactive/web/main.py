#!/usr/bin/env python3
"""
AgenticStack — Interactive Web Test Client

Usage:
  python -m tests.interactive.web.main
  python -m tests.interactive.web.main --port 8889 --backend http://localhost:8848

Access: http://localhost:8889
"""

import argparse
import logging
import sys
from pathlib import Path

# Make the repo root importable when run directly
sys.path.insert(0, str(Path(__file__).parents[4]))

import uvicorn
import tests.interactive.web.server as _server

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgenticStack interactive web test client")
    parser.add_argument("--port",     type=int, default=8889,                      help="Port to serve the dashboard on (default: 8889)")
    parser.add_argument("--backend",  default="http://localhost:8848",             help="AgenticStack backend URL (default: http://localhost:8848)")
    parser.add_argument("--self-url", default=None,                                help="Public URL of this test client (default: http://localhost:{port}). Set when running behind Docker/proxy so AgenticStack can reach the callback endpoint.")
    args = parser.parse_args()

    _server.BACKEND_API = args.backend.rstrip("/")

    # When the backend runs in Docker it cannot reach "localhost" on the host.
    # Default to host.docker.internal so callbacks work out of the box on
    # Docker Desktop (Mac/Windows). Override with --self-url for other setups.
    default_self_url = f"http://host.docker.internal:{args.port}"
    _server.SELF_URL  = (args.self_url or default_self_url).rstrip("/")

    logging.basicConfig(level=logging.INFO, force=True)
    logger.info("[test-main] starting interactive web client port=%s backend=%s self_url=%s", args.port, _server.BACKEND_API, _server.SELF_URL)
    print(f"\nAgenticStack — Interactive Web Test Client")
    print(f"  Dashboard   : http://localhost:{args.port}")
    print(f"  Backend     : {_server.BACKEND_API}")
    print(f"  Callback URL: {_server.SELF_URL}/callback/{{user_id}}\n")

    uvicorn.run(_server.app, host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
