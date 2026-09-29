#!/usr/bin/env bash
# Deploy only when explicitly invoked; run in the foreground for visible errors.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 "$project_dir/android/scripts/run_on_device.py" "$@"
