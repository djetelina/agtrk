"""Tests for version_check module."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from packaging.version import Version

from agtrk.version_check import get_latest_pypi_version


@pytest.mark.anyio
async def test_returns_version_on_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {"info": {"version": "2.0.0"}}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agtrk.version_check.httpx.AsyncClient", return_value=mock_client):
        result = await get_latest_pypi_version()

    assert result == Version("2.0.0")


@pytest.mark.anyio
async def test_returns_none_on_timeout():
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.TimeoutException("timeout")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agtrk.version_check.httpx.AsyncClient", return_value=mock_client):
        result = await get_latest_pypi_version()

    assert result is None


@pytest.mark.anyio
async def test_returns_none_on_network_error():
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ConnectError("connection refused")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agtrk.version_check.httpx.AsyncClient", return_value=mock_client):
        result = await get_latest_pypi_version()

    assert result is None


@pytest.mark.anyio
async def test_returns_none_on_bad_json():
    mock_response = MagicMock()
    mock_response.json.return_value = {"unexpected": "data"}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agtrk.version_check.httpx.AsyncClient", return_value=mock_client):
        result = await get_latest_pypi_version()

    assert result is None
