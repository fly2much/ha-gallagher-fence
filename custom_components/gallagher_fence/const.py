"""Constants for the Gallagher Fence (read-only) integration."""
DOMAIN = "gallagher_fence"

API_BASE = "https://am.app.gallagher.com/amc/iot/api"
USER_AGENT = "Gallagher%20Devices/1.0.921 CFNetwork/3896.100.1.2.1 Darwin/27.0.0"

CONF_FARM_ID = "farm_id"
CONF_REFRESH_TOKEN = "refresh_token"

CONF_SCAN_MINUTES = "scan_minutes"
CONF_STALE_HOURS = "stale_hours"
DEFAULT_SCAN_MINUTES = 5
DEFAULT_STALE_HOURS = 3

# Zones whose last reading is this much older than the newest reading on the
# same energiser are treated as leftovers from replaced monitors and skipped.
STALE_ZONE_DAYS = 30
