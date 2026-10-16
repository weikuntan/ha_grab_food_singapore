"""Shared fixtures."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grab_food_sg.const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRY,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load custom_components/ during tests."""
    yield


@pytest.fixture
async def setup_entry(hass) -> AsyncGenerator[Callable[..., Awaitable[MockConfigEntry]]]:
    """Return a factory that adds + sets up a config entry, and unloads it after."""
    entries: list[MockConfigEntry] = []

    async def _setup(
        *,
        access_token: str = "eyJ.access.token",
        refresh_token: str = "",
        token_expiry: float | None = None,
        **_: Any,
    ) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Grab Food SG",
            data={
                CONF_ACCESS_TOKEN: access_token,
                CONF_REFRESH_TOKEN: refresh_token,
                CONF_TOKEN_EXPIRY: (
                    token_expiry if token_expiry is not None else time.time() + 3600
                ),
            },
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entries.append(entry)
        return entry

    yield _setup

    for entry in entries:
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
