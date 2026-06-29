from dragonpilot.settings import tr

ITEMS = [
  {
    "section": "Device",
    "key": "dp_dev_quick_start",
    "type": "toggle_item",
    "title": lambda: tr("Quick Start"),
    "description": lambda: tr("Skips Git operations on startup by creating a prebuilt marker file in the openpilot directory."),
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "0",
  },
]
