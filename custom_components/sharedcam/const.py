"""Constants for the SharedCam integration."""
from datetime import timedelta

DOMAIN = "sharedcam"

CONF_GO2RTC_URL = "go2rtc_url"
CONF_FRIGATE_URL = "frigate_url"
CONF_CAMERA_NAME = "camera_name"
CONF_FRIENDLY_NAME = "friendly_name"

DEFAULT_GO2RTC_URL = "http://localhost:1984"
DEFAULT_FRIGATE_URL = "rtsp://localhost:8554"

SCAN_INTERVAL = timedelta(seconds=30)

# Optional Jinja2 template (stored in entry.options) rendered to a plain string
# and surfaced as "status" in the /status JSON endpoint and SSE stream.
CONF_STATUS_TEMPLATE = "status_template"

# When False, the /status endpoint and SSE stream send `"viewers": null` instead
# of the live count — useful when the owner doesn't want to expose viewer numbers.
CONF_SHOW_VIEWERS = "show_viewers"
