#!/usr/bin/env python3
"""Live check for Grab Food Singapore, with no Home Assistant and no HACS.

Runs the integration's own API client and order parser against Grab's real
endpoints using your token, and reports what came back.

    pip install aiohttp
    export GRAB_ACCESS_TOKEN='eyJ...'        # required
    export GRAB_REFRESH_TOKEN='...'          # optional
    python scripts/live_check.py

Best run while you have an order in progress, otherwise it can only confirm
that the endpoint answers and the token is accepted.

By default the output shows only the *shape* of Grab's response (key names and
value types, with order status and currency shown in full) and whether each
sensor field is populated, so it is safe to paste into an issue. Use
--show-values to print the parsed values too, and --show-body for the raw
response. Both contain personal data (address, driver name).

Your token is read from the environment and is never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
import time
import types
from pathlib import Path

try:
    import aiohttp
except ImportError:  # pragma: no cover
    sys.exit("This script needs aiohttp:  pip install aiohttp")

COMPONENT_DIR = (
    Path(__file__).resolve().parent.parent / "custom_components" / "grab_food_sg"
)
PKG = "grab_food_sg_live"
KEEP_VALUES = {"state", "status", "orderState", "currency"}


def _stub_homeassistant() -> None:
    """Minimal stand-ins so coordinator.py imports without Home Assistant."""

    def mod(name: str) -> types.ModuleType:
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m

    mod("homeassistant")
    mod("homeassistant.helpers")
    mod("homeassistant.config_entries").ConfigEntry = type("ConfigEntry", (), {})
    mod("homeassistant.core").HomeAssistant = type("HomeAssistant", (), {})
    mod("homeassistant.exceptions").ConfigEntryAuthFailed = type(
        "ConfigEntryAuthFailed", (Exception,), {}
    )

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, *args, **kwargs):
            pass

    mod("homeassistant.helpers.update_coordinator").DataUpdateCoordinator = (
        DataUpdateCoordinator
    )


def shape(obj, key=None):
    """Describe a JSON value without leaking personal data."""
    if isinstance(obj, dict):
        return {k: shape(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        if not obj:
            return []
        out = [shape(obj[0], key)]
        if len(obj) > 1:
            out.append(f"... {len(obj)} items")
        return out
    if isinstance(obj, str):
        return obj if key in KEEP_VALUES else f"<str:{len(obj)}>"
    if obj is None:
        return None
    return f"<{type(obj).__name__}>"


def _print_json(label: str, value) -> None:
    import json

    print(f"    {label}:")
    for line in json.dumps(value, indent=2, ensure_ascii=False).splitlines():
        print(f"      {line}")


async def run(args: argparse.Namespace) -> int:
    token = os.environ.get("GRAB_ACCESS_TOKEN", "").strip()
    if not token:
        print("Set GRAB_ACCESS_TOKEN first (the value after 'Bearer ').")
        return 2
    refresh = os.environ.get("GRAB_REFRESH_TOKEN", "").strip()

    _stub_homeassistant()
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(COMPONENT_DIR)]
    sys.modules[PKG] = pkg

    const = importlib.import_module(f"{PKG}.const")
    if args.food_base:
        base = args.food_base.rstrip("/")
        const.GRAB_FOOD_BASE = base
        const.GRAB_ORDERS_ACTIVE = f"{base}/v2/orders/active"
        const.GRAB_ORDERS_HISTORY = f"{base}/v2/orders/history"
        const.GRAB_ORDER_DETAIL = f"{base}/v2/orders"
    if args.active_url:
        const.GRAB_ORDERS_ACTIVE = args.active_url
    # Imported after the overrides so they take effect.
    api = importlib.import_module(f"{PKG}.api")
    coordinator = importlib.import_module(f"{PKG}.coordinator")

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession() as session:
        # ── 1. Raw probe of the active-orders endpoint ──────────────────────
        url = const.GRAB_ORDERS_ACTIVE
        print(f"[1] GET {url}")
        headers = {**api._COMMON_HEADERS, "Authorization": f"Bearer {token}"}
        try:
            async with session.get(
                url, headers=headers, allow_redirects=False, timeout=timeout
            ) as resp:
                body = await resp.text()
                ctype = resp.headers.get("Content-Type", "")
                print(f"    HTTP {resp.status}   content-type: {ctype or '-'}")
                if resp.status in (301, 302, 303, 307, 308):
                    print(f"    redirected to: {resp.headers.get('Location', '?')}")
                    print("    -> endpoint has moved; update the URL in const.py")
                elif "json" in ctype:
                    import json

                    try:
                        _print_json("response shape", shape(json.loads(body)))
                    except ValueError:
                        print("    (claims JSON but did not parse)")
                else:
                    print(f"    non-JSON response, starts: {body[:120]!r}")
                if args.show_body:
                    print(f"    raw body (first 2000 chars):\n{body[:2000]}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            print(f"    network error: {err}")
            return 1

        # ── 2. Through the integration's own client ─────────────────────────
        print("\n[2] Integration client: get_active_orders()")
        client = api.GrabFoodApiClient(
            session,
            access_token=token,
            refresh_token=refresh,
            token_expiry=time.time() + 3600,
        )
        try:
            orders = await client.get_active_orders()
        except api.GrabAuthError as err:
            print(f"    AUTH FAILED: {err}")
            print("    -> token expired/invalid, or Grab expects different auth")
            return 1
        except api.GrabApiError as err:
            print(f"    API ERROR: {str(err)[:300]}")
            return 1

        if not orders:
            print("    OK: endpoint answered, token accepted, no active order.")
            print("    Place an order and run again to check the order parsing.")
            return 0
        print(f"    OK: {len(orders)} active order(s)")

        order = orders[0]
        order_id = order.get("orderID") or order.get("id") or order.get("order_id", "")
        detail: dict = {}
        print(f"\n[3] Order detail: {const.GRAB_ORDER_DETAIL}/<order id>")
        if order_id:
            try:
                detail = await client.get_order_detail(str(order_id))
                _print_json("detail shape", shape(detail))
            except api.GrabApiError as err:
                print(f"    detail call failed (non-fatal): {str(err)[:200]}")
        else:
            print("    no order id found in the active-order payload")

        # ── 4. Parse exactly as the coordinator does ────────────────────────
        print("\n[4] Parsed sensor values")
        parsed = coordinator.GrabFoodCoordinator.__new__(
            coordinator.GrabFoodCoordinator
        )._parse_order(order, detail)
        always_show = {"status", "currency", "item_count"}
        for key, value in parsed.items():
            if key == "raw":
                continue
            empty = value in ("", None, [], 0) and key != "item_count"
            if args.show_values or key in always_show:
                shown = value
            else:
                shown = "(empty)" if empty else "(populated)"
            flag = "  <-- EMPTY, parser found no matching field" if empty else ""
            print(f"    {key:<18} {shown}{flag}")
        known = set(const.ORDER_STATES)
        if parsed["status"] not in known:
            print(
                f"\n    NOTE: status {parsed['status']!r} is not one of the states "
                "the integration knows about."
            )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--food-base", help="override the food API base URL")
    parser.add_argument("--active-url", help="override the active-orders URL")
    parser.add_argument("--show-values", action="store_true", help="print parsed values")
    parser.add_argument("--show-body", action="store_true", help="print raw response")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
