#!/usr/bin/env python3
"""Fail unless every recorded ORT operator kernel used QNNExecutionProvider.

ORT records host scheduling on CPU threads even when kernels execute on an NPU.
This checks kernel providers, not event thread IDs. QNN can itself use CPU/GPU
backends, so the server must separately pin libQnnHtp.so; this trace cannot prove
which QNN backend was loaded. Obtain the complete JSON after ending profiling.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


class ProfileError(ValueError):
    pass


def verify_profile(document) -> dict:
    events = document.get("traceEvents") if isinstance(document, dict) else document
    if not isinstance(events, list) or not events:
        raise ProfileError("Profile must contain a nonempty event list")
    providers = Counter()
    total_duration_us = 0.0
    for event in events:
        if not isinstance(event, dict):
            raise ProfileError("Profile contains a malformed event")
        name = event.get("name", "")
        args = event.get("args", {})
        if not isinstance(name, str) or not isinstance(args, dict):
            raise ProfileError("Profile contains a malformed event name or args")
        # Old ORT profiles include fences without provider attribution. Fences
        # synchronize scheduling and are not operator execution events.
        is_fence = name.endswith(("_fence_before", "_fence_after"))
        is_kernel = name.endswith("_kernel_time") or "provider" in args
        is_unattributed_node = event.get("cat") == "Node" and not is_fence
        if not is_kernel and not is_unattributed_node:
            continue
        provider = args.get("provider")
        if not isinstance(provider, str) or not provider:
            raise ProfileError(f"Kernel event {name!r} has no provider attribution")
        if provider != "QNNExecutionProvider":
            raise ProfileError(f"Kernel event {name!r} ran on forbidden provider {provider!r}")
        if event.get("ph") != "X":
            raise ProfileError(f"Kernel event {name!r} is not a complete duration event")
        duration = event.get("dur")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 0 <= duration < float("inf"):
            raise ProfileError(f"Kernel event {name!r} has invalid duration")
        providers[provider] += 1
        total_duration_us += duration
    if not providers:
        raise ProfileError("No attributed QNN kernel execution was recorded")
    return {"status": "qnn_only", "kernel_events": sum(providers.values()),
            "providers": dict(providers), "kernel_duration_us": total_duration_us,
            "backend_requirement": "Server must also pin libQnnHtp.so; ORT provider traces alone do not identify the QNN backend."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    try:
        result = verify_profile(json.loads(args.profile.read_text()))
    except (OSError, ValueError) as error:
        print(f"Profile verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
