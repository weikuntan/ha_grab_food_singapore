# Grab Food Singapore

> **Unofficial** Home Assistant integration — not affiliated with or endorsed by Grab Holdings.
> Singapore port of [simplemice/ha_grab_food_thailand](https://github.com/simplemice/ha_grab_food_thailand) (GPL-3.0).

Track your active GrabFood orders in Singapore inside Home Assistant: when the food is picked up, where the driver is, and when it arrives, without opening the app.

> **Status: untested against Singapore.** This port reuses the Thailand integration's API endpoints, which are Grab's internal mobile/web endpoints, not a documented public API. Only the region settings (country header, locale, currency) were changed. If sensors stay at `no_active_order` during a real order, enable debug logging and check which endpoint responds — all URLs live in `custom_components/grab_food_sg/const.py`.

---

## What you get

9 sensors, updated every 30 seconds while an order is active and every 5 minutes when idle:

| Sensor                 | Entity ID                                  | What it shows                                                                     |
| ---------------------- | ------------------------------------------ | --------------------------------------------------------------------------------- |
| **Order Status**       | `sensor.grab_food_sg_order_status`         | Lifecycle state (placed → confirmed → preparing → delivering → delivered)         |
| **Restaurant**         | `sensor.grab_food_sg_restaurant`           | Restaurant name                                                                   |
| **Order Total**        | `sensor.grab_food_sg_order_total`          | Price in SGD                                                                      |
| **Estimated Delivery** | `sensor.grab_food_sg_estimated_delivery`   | ETA as a time string or ISO timestamp                                             |
| **Driver**             | `sensor.grab_food_sg_driver`               | Driver name, with GPS `latitude` / `longitude` as attributes                      |
| **Driver Plate**       | `sensor.grab_food_sg_driver_plate`         | Vehicle licence plate                                                             |
| **Items Ordered**      | `sensor.grab_food_sg_items_ordered`        | Item count, with item names as an attribute                                       |
| **Order ID**           | `sensor.grab_food_sg_order_id`             | Grab order reference                                                              |
| **Delivery Address**   | `sensor.grab_food_sg_delivery_address`     | Drop-off address                                                                  |

The integration uses its own domain (`grab_food_sg`), so it can be installed next to the Thailand version.

---

## Requirements

- Home Assistant **2024.1** or newer
- A **Grab account** with GrabFood orders in Singapore
- Your Grab **access token** (see below)

## Installation

### Via HACS (recommended)

1. **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/weikuntan/ha_grab_food_singapore` as category **Integration**
3. Search for **Grab Food Singapore** and click **Download**
4. Restart Home Assistant

### Manual

Copy `custom_components/grab_food_sg/` into your HA `config/custom_components/` directory and restart.

---

## Getting your token

The integration authenticates with a bearer token from your Grab session.

**Option A — browser (quickest)**

1. Sign in at [food.grab.com/sg](https://food.grab.com/sg)
2. Open developer tools (F12) → **Application** → **Local Storage** → `food.grab.com`
3. Copy the value of `access_token` (a long string starting with `eyJ`)

Browser tokens usually expire within hours and typically come without a refresh token, so expect to re-authenticate often.

**Option B — Android app (longer-lived)**

Use a traffic-capture app such as HTTPCanary on Android, open the Grab app, and copy the part after `Bearer ` from the `Authorization` header of any request to a Grab domain. If the same capture shows a `refresh_token`, copy it too — with it the integration renews its own token. Recent Android versions and Grab's certificate pinning may require a rooted device or emulator for this.

Then: **Settings → Devices & Services → Add Integration → Grab Food Singapore**, paste the access token (and refresh token if you have one) and submit.

### Re-authentication

When the token expires and no refresh token is available, Home Assistant prompts you to re-authenticate. Paste a fresh token and the sensors resume.

---

## Order status states

| State             | Meaning                       |
| ----------------- | ----------------------------- |
| `no_active_order` | No order in progress          |
| `placed`          | Order submitted to restaurant |
| `confirmed`       | Restaurant accepted the order |
| `preparing`       | Food is being prepared        |
| `driver_assigned` | A driver has been matched     |
| `picked_up`       | Driver collected the food     |
| `delivering`      | Driver is on the way          |
| `delivered`       | Order delivered successfully  |
| `cancelled`       | Order was cancelled           |

---

## Automation examples

### Announce when food is picked up

```yaml
alias: "Grab Food SG — picked up announcement"
trigger:
  - platform: state
    entity_id: sensor.grab_food_sg_order_status
    to: picked_up
action:
  - service: tts.speak
    target:
      entity_id: media_player.living_room
    data:
      message: >
        Your order from {{ states('sensor.grab_food_sg_restaurant') }}
        has been picked up. ETA {{ states('sensor.grab_food_sg_estimated_delivery') }}.
```

### Push notification on delivery

```yaml
alias: "Grab Food SG — delivered notification"
trigger:
  - platform: state
    entity_id: sensor.grab_food_sg_order_status
    to: delivered
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "🍔 Food delivered!"
      message: >
        {{ states('sensor.grab_food_sg_restaurant') }} ·
        S${{ states('sensor.grab_food_sg_order_total') }} ·
        {{ states('sensor.grab_food_sg_items_ordered') }} items
```

### Dashboard card — live order summary

```yaml
type: entities
title: Grab Food Order
entities:
  - sensor.grab_food_sg_order_status
  - sensor.grab_food_sg_restaurant
  - sensor.grab_food_sg_estimated_delivery
  - sensor.grab_food_sg_driver
  - sensor.grab_food_sg_order_total
  - sensor.grab_food_sg_items_ordered
```

### Dashboard card — driver on a map

```yaml
type: map
entities:
  - entity: sensor.grab_food_sg_driver
    label_mode: state
```

The driver's position is in the `latitude` / `longitude` attributes of `sensor.grab_food_sg_driver`.

---

## How it works

```
config_flow  →  paste access token (+ optional refresh token)
__init__     →  creates API client and coordinator, forwards to sensor platform
coordinator  →  polls Grab on an adaptive schedule; persists refreshed tokens
sensor       →  9 CoordinatorEntity sensors, each reading one field
api          →  async aiohttp client: auth, token refresh, order fetch
const        →  API URLs and region settings (country, locale, currency)
```

## Limitations

- **Unofficial API** — endpoints, field names and auth can change without notice.
- **Singapore endpoints unverified** — see the status note at the top.
- **One active order** — the integration tracks the first active order returned.
- **Rate limits** — defaults (30 s / 5 min) are deliberately conservative.

## License

GPL-3.0, inherited from the upstream project. See [LICENSE](LICENSE).
