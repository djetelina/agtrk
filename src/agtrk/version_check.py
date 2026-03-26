"""Check PyPI for newer agtrk versions."""

import httpx
from packaging.version import Version

from agtrk import __version__


async def get_latest_pypi_version() -> Version | None:
    """Return the latest version on PyPI, or *None* on any failure."""
    async with httpx.AsyncClient(headers={"User-Agent": f"agtrk v{__version__}"}) as client:
        try:
            r = await client.get("https://pypi.org/pypi/agtrk/json", timeout=3.0)
            return Version(r.json()["info"]["version"])
        except Exception:
            return None
