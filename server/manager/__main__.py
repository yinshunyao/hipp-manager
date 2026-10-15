"""python -m manager"""

from __future__ import annotations

import sys

import uvicorn

from manager.config import load_settings
from manager.app import create_app


def main() -> int:
    settings = load_settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
