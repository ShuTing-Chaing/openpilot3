# C3XL / OnePlus 15T OPIF source snapshot

Base: `dev-sp-8E5@631ccadcdbbe854e7eea318f14e67a1839897351`. This branch contains C3XL OPIF routing, local-model hot standby, USB and dedicated-hotspot transport, and the Android OPIF App source. It contains no phone hotspot password, device profile, APK, model weights, or raw device logs.

The last tested App used the ordinary CPU history buffers. The experimental `QnnHtpShared` history-buffer change was built but not installed or E2E tested, so it is excluded here. The installed App APK SHA256 at that point was `95d5c617e6c0e6afd03c4d424e963e2b267e3ced4cfd1dab4b1f8693b2737b1c`; model SHA256 was `8cf7714f5d4f2601f273a7f4b7eddba25c9c6dbb8b38962c7600cda1fbd85961`.

The previous offroad fixed-input USB and hotspot runs each completed 1,200/1,200 frames at 20 Hz with byte-identical retained outputs and no expired frames. They do not establish onroad qualification. The MAC-free hotspot discovery change in this snapshot was requested after testing was paused; it has not been installed on C3XL or verified on the device. Until its E2E gates in `latency-optimization/FAILURES_AND_E2E.md` pass, do not update the existing source-hash qualification record to treat this commit as the tested device version.

The Android service requests the configured C3 hotspot as a local-only network when the user manually opens the App. `hotspot.json` is created in the App's private files directory by `tools/sp8e5/provision_phone_hotspot.py` on the paired C3XL; its contents are never stored in Git. Automatic start after phone cold boot is outside scope.
