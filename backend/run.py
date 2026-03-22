#!/usr/bin/env python3
"""
run.py — convenience launcher for the NeuroScan FastAPI backend.

    python run.py              # dev mode with hot-reload
    python run.py --prod       # production mode, no reload
    python run.py --port 9000  # custom port
"""

import argparse
import uvicorn
from app.core.config import settings


def main():
    parser = argparse.ArgumentParser(description="NeuroScan API server")
    parser.add_argument("--host",   default=settings.host,  help="Bind host")
    parser.add_argument("--port",   default=settings.port,  type=int, help="Bind port")
    parser.add_argument("--prod",   action="store_true",    help="Production mode (no reload)")
    args = parser.parse_args()

    is_dev = not args.prod

    print(f"\n  NeuroScan API")
    print(f"  http://{args.host}:{args.port}")
    print(f"  Docs  → http://localhost:{args.port}/docs")
    print(f"  Mode  → {'development' if is_dev else 'production'}\n")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=is_dev,
        log_level="info" if is_dev else "warning",
        access_log=is_dev,
    )


if __name__ == "__main__":
    main()
