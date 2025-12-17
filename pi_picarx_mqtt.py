#!/usr/bin/env python3
import json, time, threading
import paho.mqtt.client as mqtt
from picarx import Picarx

# ==== 設定 ====
BROKER_HOST = "3.112.216.187"
BROKER_PORT = 1883                # ブラウザは9001(WS)、Piは1883(TCP)が安定
TOPIC_CMD   = "demo/picarx/cmd"        # { "throttle": -1..1, "steer": -1..1 }
TOPIC_PT    = "demo/picarx/camera"     # { "pan": -45..45, "tilt": -30..30 }
TOPIC_PING  = "demo/picarx/ping"
TOPIC_TELE  = "demo/picarx/telemetry"
CLIENT_ID   = "picarx-driver-1"

# ステアリング角度の最大値（度）
DIR_SERVO_MAX_ANGLE = 30

# ==== PiCarX インスタンス ====
px = Picarx()

# ==== PiCarX 制御関数 ====
def drive(throttle: float, steer: float):
    """
    throttle: -1.0 (後退最大) 〜 +1.0 (前進最大)
    steer: -1.0 (左最大) 〜 +1.0 (右最大)
    """
    print(f"[DRIVE] throttle={throttle:.2f}, steer={steer:.2f}")

    # ステアリング角度を設定 (-30〜+30度)
    steer_angle = int(steer * DIR_SERVO_MAX_ANGLE)
    steer_angle = max(-DIR_SERVO_MAX_ANGLE, min(DIR_SERVO_MAX_ANGLE, steer_angle))
    px.set_dir_servo_angle(steer_angle)

    # 速度を計算 (0〜100)
    speed = int(abs(throttle) * 100)
    speed = max(0, min(100, speed))

    if throttle > 0.01:
        px.forward(speed)
    elif throttle < -0.01:
        px.backward(speed)
    else:
        px.stop()

def camera_move(pan_deg: float, tilt_deg: float):
    """
    pan_deg: カメラ水平角度 (-90〜+90度、0が正面)
    tilt_deg: カメラ垂直角度 (-35〜+65度、0が正面)
    """
    print(f"[CAMERA] pan={pan_deg:.1f}°, tilt={tilt_deg:.1f}°")

    # パン角度を設定 (-90〜+90度)
    pan_deg = max(-90, min(90, pan_deg))
    px.set_cam_pan_angle(pan_deg)

    # チルト角度を設定 (-35〜+65度)
    tilt_deg = max(-35, min(65, tilt_deg))
    px.set_cam_tilt_angle(tilt_deg)

def on_connect(client, userdata, flags, rc, props=None):
    print("MQTT connected:", rc)
    client.subscribe([(TOPIC_CMD, 0), (TOPIC_PT, 0)])
    print("Subscribed:", TOPIC_CMD)
    # LWT 監視用に生存信号（任意）
    def _ping():
        while True:
            try:
                client.publish(TOPIC_PING, "alive", qos=0, retain=False)
            except Exception as e:
                print("ping error:", e)
            time.sleep(5)
    threading.Thread(target=_ping, daemon=True).start()

def on_message(client, userdata, msg):
    print("RX", msg.topic, msg.payload.decode(errors="ignore"))
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        print("invalid json:", msg.topic, msg.payload)
        return

    if msg.topic == TOPIC_CMD:
        throttle = float(payload.get("throttle", 0))
        steer    = float(payload.get("steer", 0))
        # clamp
        throttle = max(-1.0, min(1.0, throttle))
        steer    = max(-1.0, min(1.0, steer))
        drive(throttle, steer)

    elif msg.topic == TOPIC_PT:
        pan  = float(payload.get("pan", 0))   # -45..45 deg 想定
        tilt = float(payload.get("tilt", 0))  # -30..30 deg 想定
        camera_move(pan, tilt)

client = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv311, clean_session=True)
client.on_connect = on_connect
client.on_message = on_message
client.will_set("picarx/status", "offline", qos=0, retain=True)

client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
client.loop_forever()
