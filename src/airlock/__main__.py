"""Entry point: python -m airlock."""

import uvicorn

from airlock.app import create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=9090)
