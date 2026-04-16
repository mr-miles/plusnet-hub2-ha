"""Constants for the Plusnet Hub 2 / BT Smart Hub 2 integration."""

DOMAIN = "plusnet_hub2"
MANUFACTURER = "Plusnet / BT"

# Config entry keys
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"

# Defaults
DEFAULT_HOST = "192.168.1.254"
DEFAULT_USERNAME = "admin"
DEFAULT_SCAN_INTERVAL = 30  # seconds

# HTTP endpoints on the hub
ENDPOINT_DEVICE_LIST = "/cgi/cgi_basicMyDevice.js"
ENDPOINT_TOPOLOGY = "/cgi/cgi_owl.js"
ENDPOINT_WAN = "/nonAuth/wan_conn.xml"

# The Referer header required after firmware V35
REFERER_PAGE = "/basic_-_my_devices.htm"

# JS variable names parsed from the CGI endpoints
JS_VAR_DEVICE_LIST = "known_device_list"
JS_VAR_OWL_STATION = "owl_station"
JS_VAR_OWL_TPLG = "owl_tplg"

# Request timeout in seconds
REQUEST_TIMEOUT = 10

# How long to consider a device "home" after last seen (seconds)
CONSIDER_HOME = 180
