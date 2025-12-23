# Task Completion Checklist
- Re-run the relevant entrypoint(s) you changed (e.g., `stream_livekit.py`, `stream_stereo_livekit.py`, `pi_picarx_mqtt.py`, viewer HTML/JS) to ensure they launch, connect to LiveKit/MQTT, and behave as expected.
- If LiveKit connectivity or permissions were touched, run `python3 test_livekit_connect.py` (with the updated token) to confirm `canSubscribe: true` and TURN access still work.
- For front-end edits, open `viewer.combined.html` or `viewer.vr.html` in a browser (Quest or desktop) and verify LiveKit subscribe + MQTT control flows.
- Update README or docs (VR_IMPLEMENTATION_STATUS.md, docs/VR_STEREO_*) when architecture, tokens, or operational steps change.
- Confirm hardware-specific instructions (camera IDs, rpicam flags, MQTT topics) remain accurate after modifications.