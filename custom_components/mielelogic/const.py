"""Constants for the Miele Logic integration."""

DOMAIN = "mielelogic"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_COUNTRY = "country"

AUTH_URL = "https://sec.mielelogic.com/v7/token"
API_URL = "https://api.mielelogic.com/v7"
CLIENT_ID = "YV1ZAQ7BTE9IT2ZBZXLJ"

COUNTRY_CODES = {
    "dk": "DA",
    "se": "SE",
    "no": "NO",
    "fi": "FI",
    "de": "DE",
}

MACHINE_TYPES = {
    "51": "washer",
    "57": "dryer",
}

SCAN_INTERVAL_SECONDS = 120

ATTR_MACHINE_NUMBER = "machine_number"
ATTR_MACHINE_NAME = "machine_name"
ATTR_MACHINE_TYPE = "machine_type"
ATTR_LAUNDRY_NUMBER = "laundry_number"
ATTR_START = "start"
ATTR_END = "end"
