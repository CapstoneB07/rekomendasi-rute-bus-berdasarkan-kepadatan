import os
from datetime import datetime

import redis
import paho.mqtt.client as mqtt


# ============================================================
# KONFIGURASI - DIPERTAHANKAN DARI VERSI YANG SEBELUMNYA
# ============================================================

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883

# PERTAHANKAN TOPIC YANG SUDAH TERBUKTI BEKERJA
MQTT_TOPIC = "capstone/stefany/esp32s3/camera/base64"

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# PERTAHANKAN QUEUE YANG SAMA DENGAN VERSI SEBELUMNYA
REDIS_QUEUE_NAME = "cv_task_queue:Koridor_Test_Lokal"

# ============================================================
# SIMPAN GAMBAR
# ============================================================

SAVE_RECEIVED_IMAGES = True
SAVE_DIR = "received_images"

message_count = 0
saved_count = 0


# ============================================================
# REDIS
# ============================================================

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB
)


# ============================================================
# UTILITY
# ============================================================

def get_timestamp():
    return datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )[:-3]


def save_image(image_bytes):
    """
    Menulis payload binary langsung ke file JPEG.
    Tidak ada Base64 decode dan tidak ada JPEG re-encode.
    """
    global saved_count

    if not SAVE_RECEIVED_IMAGES:
        return None

    os.makedirs(
        SAVE_DIR,
        exist_ok=True
    )

    saved_count += 1

    filename = (
        f"{get_timestamp()}_"
        f"frame_{saved_count:06d}.jpg"
    )

    filepath = os.path.join(
        SAVE_DIR,
        filename
    )

    with open(filepath, "wb") as f:
        f.write(image_bytes)

    return filepath


# ============================================================
# MQTT CALLBACK
# ============================================================

def on_connect(client, userdata, flags, rc):
    print(
        f"[MQTT SERVICE] on_connect dipanggil | rc={rc}"
    )

    if rc == 0:
        print(
            "[MQTT SERVICE] Terhubung ke HiveMQ."
        )

        result, mid = client.subscribe(
            MQTT_TOPIC,
            qos=0
        )

        print(
            "[MQTT SERVICE] Subscribe request | "
            f"topic={MQTT_TOPIC} | "
            f"result={result} | mid={mid}"
        )

    else:
        print(
            "[MQTT SERVICE] "
            f"Gagal terhubung | rc={rc}"
        )


def on_subscribe(client, userdata, mid, granted_qos):
    print(
        "[MQTT SERVICE] Subscription berhasil | "
        f"mid={mid} | qos={granted_qos}"
    )


def on_message(client, userdata, msg):
    global message_count

    try:
        message_count += 1

        # ====================================================
        # RAW BINARY - JANGAN decode UTF-8
        # ====================================================

        image_bytes = msg.payload

        print(
            "\n[MQTT SERVICE] MESSAGE MASUK | "
            f"count={message_count}"
        )

        print(
            f"[MQTT SERVICE] topic={msg.topic}"
        )

        print(
            f"[MQTT SERVICE] payload_size="
            f"{len(image_bytes)} bytes "
            f"({len(image_bytes) / 1024:.2f} KB)"
        )

        if not image_bytes:
            print(
                "[MQTT WARNING] Payload kosong."
            )
            return

        # ====================================================
        # SIMPAN VISUAL
        # ====================================================

        saved_path = save_image(
            image_bytes
        )

        if saved_path:
            print(
                "[MQTT SERVICE] "
                f"Gambar tersimpan: {saved_path}"
            )

        # ====================================================
        # REDIS
        # ====================================================

        redis_client.lpush(
            REDIS_QUEUE_NAME,
            image_bytes
        )

        print(
            "[MQTT SERVICE] "
            "Payload raw binary diteruskan ke Redis | "
            f"queue={REDIS_QUEUE_NAME}"
        )

    except Exception as e:
        print(
            "[MQTT ERROR] "
            f"{type(e).__name__}: {e}"
        )


def on_disconnect(client, userdata, rc):
    print(
        "[MQTT SERVICE] "
        f"Terputus dari broker | rc={rc}"
    )


# ============================================================
# START
# ============================================================

mqtt_client = mqtt.Client()

mqtt_client.on_connect = on_connect
mqtt_client.on_subscribe = on_subscribe
mqtt_client.on_message = on_message
mqtt_client.on_disconnect = on_disconnect

print(
    "[INFO] Menjalankan MQTT Subscriber..."
)

print(
    f"[INFO] Broker = {MQTT_BROKER}:{MQTT_PORT}"
)

print(
    f"[INFO] Topic  = {MQTT_TOPIC}"
)

print(
    "[INFO] Payload = RAW BINARY"
)

print(
    f"[INFO] Save   = {SAVE_RECEIVED_IMAGES}"
)

print(
    f"[INFO] Folder = {os.path.abspath(SAVE_DIR)}"
)

print(
    f"[INFO] Redis  = {REDIS_QUEUE_NAME}"
)

try:
    mqtt_client.connect(
        MQTT_BROKER,
        MQTT_PORT,
        60
    )

    mqtt_client.loop_forever()

except KeyboardInterrupt:
    print(
        "\n[INFO] MQTT Subscriber dihentikan."
    )

except Exception as e:
    print(
        f"[MQTT FATAL] "
        f"{type(e).__name__}: {e}"
    )
