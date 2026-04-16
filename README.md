# Plusnet Hub 2 / BT Smart Hub 2 — Home Assistant Integration

A HACS-compatible custom integration for Home Assistant that provides **presence detection** (device tracking) via the Plusnet Hub 2 or BT Smart Hub 2 router's local web interface.

## Why This Exists

The built-in `bt_smarthub` integration in Home Assistant:
- Has no UI config flow (YAML-only)
- Accepts no username or password fields
- Uses a synchronous third-party library (`btsmarthub_devicelist`) that violates HA's async requirements
- Has no `DataUpdateCoordinator` — each entity polls independently
- Has fragile JS-parsing code that breaks on firmware updates

This integration is a full rewrite using native `aiohttp`, a `DataUpdateCoordinator`, a proper UI config flow, and robust JS parsing.

## Compatibility

| Hardware | Status |
|---|---|
| Plusnet Hub 2 | Tested target |
| BT Smart Hub 2 | Same hardware, same endpoints |
| EE Smart Hub (white) | Same hardware, should work |
| BT Smart Hub (original) | Uses different endpoints — not supported |

## How It Works

The hub exposes connected device information via two JavaScript CGI endpoints that are accessible on the local network **without authentication**:

- `http://192.168.1.254/cgi/cgi_basicMyDevice.js` — list of known devices (MAC, IP, hostname, active status)
- `http://192.168.1.254/cgi/cgi_owl.js` — network topology (connection type: Ethernet/2.4GHz/5GHz)

Since firmware update V35 (~mid-2022), requests to these endpoints require a `Referer` header:
```
Referer: http://192.168.1.254/basic_-_my_devices.htm
```

This integration always sends this header. The username and password you enter in the config flow are stored for future-proofing but are not currently required by the endpoints.

## Installation via HACS

1. Open HACS in Home Assistant
2. Go to **Integrations** → click the three dots in the top right → **Custom repositories**
3. Add `https://github.com/YOUR_USERNAME/plusnet-hub2-ha` with category **Integration**
4. Find "Plusnet Hub 2 / BT Smart Hub 2" in the HACS integration list and click **Download**
5. Restart Home Assistant
6. Go to **Settings** → **Devices & Services** → **Add Integration** → search for "Plusnet Hub 2"

## Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/plusnet_hub2/` folder into your HA config directory:
   ```
   config/
   └── custom_components/
       └── plusnet_hub2/
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── coordinator.py
           ├── device_tracker.py
           ├── const.py
           ├── strings.json
           └── translations/
               └── en.json
   ```
3. Restart Home Assistant
4. Go to **Settings** → **Devices & Services** → **Add Integration** → search for "Plusnet Hub 2"

## Configuration

Fill in the config flow form:

| Field | Default | Description |
|---|---|---|
| **Hub IP address** | `192.168.1.254` | Change only if you have a non-standard LAN setup |
| **Username** | `admin` | Leave as `admin` for most setups |
| **Admin password** | _(blank)_ | Printed on the label on the back of the hub |

After setup, you can change the **scan interval** via the integration's Options:
- **Settings** → **Devices & Services** → Plusnet Hub 2 → **Configure**
- Range: 10–3600 seconds (default: 30 seconds)

## Finding Device MAC Addresses

Each tracked device creates an entity like `device_tracker.my_laptop`. To find a specific device's MAC address:

1. Open the entity in the Home Assistant UI
2. The MAC address is shown in the entity's attributes
3. Alternatively, check your hub's web interface at `http://192.168.1.254` → Hub Manager → My Devices

To use a device tracker for presence detection, create a [Person](https://www.home-assistant.io/integrations/person/) and assign the relevant `device_tracker.*` entity to it.

## Known Limitations

1. **No authentication on CGI endpoints**: The device list endpoints are unauthenticated. The password field is for future use. If BT/Plusnet change firmware to require auth, the integration will need updating.

2. **Active status latency**: The hub may show devices as "active" for a few minutes after they disconnect. This is a hub firmware behaviour, not an integration issue. Use the `consider_home` option in HA's person/zone settings to tune this.

3. **IPv6 devices**: The hub sometimes permanently shows IPv6 devices as active even after disconnection. This is a known firmware quirk.

4. **Hub restart**: After a hub restart the integration will fail to fetch until the hub is back online. HA will show a warning and retry automatically.

5. **Firmware changes**: The hub returns JavaScript variable declarations that this integration parses with regex. Major firmware changes could break parsing. If this happens, check the GitHub issues.

6. **SmartHub 1 not supported**: The original BT Smart Hub (model 1) uses a completely different JSON-RPC API with MD5 digest auth. Use the built-in `bt_smarthub` integration with `smarthub_model: 1` for that.

## Troubleshooting

**"Cannot connect to hub"**
- Verify the hub IP: open a browser and go to `http://192.168.1.254`
- If you use a different IP (e.g. `192.168.0.1`), enter that in the config flow

**"No devices detected" / entities not created**
- Check HA logs for parsing errors: `Settings` → `System` → `Logs`, search for `plusnet_hub2`
- The hub may have returned an unexpected response format — file a GitHub issue with the raw response

**"403 Forbidden" errors in logs**
- A firmware update may have changed the Referer requirement
- Check if the `Referer` header value needs updating for your firmware version

## Development / Testing

```bash
pip install -r requirements_test.txt
pytest tests/ -v
```

## License

MIT
