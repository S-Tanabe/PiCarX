# Suggested Commands
- `source ~/livekit-venv/bin/activate && python3 stream_livekit.py` – start single-camera low-latency LiveKit streaming from the Pi.
- `source ~/livekit-venv/bin/activate && python3 stream_stereo_livekit.py` – capture two Picamera2 feeds, combine into side-by-side stereo, and publish to LiveKit.
- `python3 pi_picarx_mqtt.py` – connect to Mosquitto on EC2 (1883) and relay MQTT drive/pan/tilt commands to the PiCar-X.
- `bash stream_whip.sh` – experimental WHIP pipeline using `rpicam-vid` + FFmpeg copy passthrough into LiveKit Ingress (<1s latency when FFmpeg has WHIP muxer).
- `python3 test_livekit_connect.py` – verify LiveKit room/token connectivity without streaming media.
- `python3 test_new_token.py` – quick token smoke test with short-lived connection.
- `cd ~/lk-api && node create-token-publish.js` – generate LiveKit publish tokens with `canSubscribe: true` on the EC2 instance.
- `docker compose restart livekit && docker compose logs livekit --tail 20` (run from `/opt/livekit` on EC2) – recycle LiveKit services if server-side changes were made.