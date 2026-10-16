"""
MQTT IMAGE + LATENCY TEST SUBSCRIBER
====================================

Untuk menguji publisher:
    KodeWifi_KirimGambardanTimestamp.ino

Payload publisher:
    {
        "timestamp": <Unix Epoch millisecond>,
        "voltage_v": <Volt>,
        "current_ma": <milliampere>,
        "power_mw": <milliwatt>,
        "image": "<Base64 JPEG>"
    }

Fungsi subscriber:
    1. Menerima pesan MQTT.
    2. Mengambil timestamp PC SECEPAT mungkin saat callback dipanggil.
    3. Menghitung latency raw dan latency setelah koreksi NTP.
    4. Decode Base64 -> JPEG.
    5. Menyimpan gambar ke folder.
    6. Mencatat ukuran payload dan ukuran JPEG.
    7. Mencatat waktu Base64 decode dan waktu save.
    8. Menyimpan semua hasil ke CSV.

Tujuan eksperimen:
    Memeriksa apakah latency ratusan ms berkaitan dengan payload
    gambar yang besar atau ada masalah lain pada pengiriman.

PENTING:
    Karena timestamp ESP32 dibuat SETELAH camera capture dan SEBELUM
    Base64 encoding + JSON + MQTT publish, maka:

        latency_corrected
        ≈ waktu Base64/JSON di ESP32
          + pengiriman MQTT
          + broker
          + network
          + waktu sampai callback subscriber

    Jadi hasil ini bukan "network-only latency murni".

Untuk network-only latency, publisher perlu menambahkan timestamp kedua
tepat sebelum client.publish().
"""

import base64
import csv
import json
import os
import socket
import statistics
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt


# ============================================================
# CONFIGURATION
# ============================================================

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "esp32s3/ina226/data"
MQTT_KEEPALIVE = 60

# NTP
NTP_SERVER = "pool.ntp.org"
NTP_PORT = 123
NTP_TIMEOUT_SEC = 3
NTP_SAMPLES = 5

# Output
CSV_LOG_FILE = "mqtt_image_latency_log.csv"
IMAGE_DIR = "received_images_latency"

# True -> simpan JPEG.
# Disarankan True untuk tujuan inspeksi dataset/payload.
SAVE_IMAGES = True

# Tampilkan statistik setiap N pesan.
PRINT_EVERY = 10


# ============================================================
# GLOBAL STATE
# ============================================================

message_count = 0
valid_count = 0
invalid_count = 0

latencies_raw = []
latencies_corrected = []

payload_sizes = []
jpeg_sizes = []
base64_decode_times = []
image_save_times = []

voltage_values = []
current_values_ma = []
power_values_mw = []

ntp_offset_ms = 0.0
ntp_rtt_ms = None

csv_file = None
csv_writer = None


# ============================================================
# TIME HELPERS
# ============================================================

def epoch_ms():
    """
    Unix epoch dalam milidetik dari clock PC.

    Dipanggil sedini mungkin di on_message().
    """
    return time.time_ns() / 1_000_000.0


def iso_from_epoch_ms(value_ms):
    dt = datetime.fromtimestamp(
        value_ms / 1000.0,
        tz=timezone.utc
    )
    return dt.isoformat(timespec="milliseconds")


# ============================================================
# NTP
# ============================================================

def query_ntp(server=NTP_SERVER, timeout=NTP_TIMEOUT_SEC):
    """
    NTP client sederhana tanpa dependency tambahan.

    Return:
        offset_ms:
            nilai yang ditambahkan ke clock lokal PC.

        round_trip_ms:
            RTT request NTP.
    """

    NTP_EPOCH = 2208988800

    packet = bytearray(48)

    # LI=0, Version=3, Mode=3 (client)
    packet[0] = 0x1B

    addr = socket.gethostbyname(server)

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    sock.settimeout(timeout)

    try:

        t1 = time.time()

        sock.sendto(
            packet,
            (addr, NTP_PORT)
        )

        data, _ = sock.recvfrom(512)

        t4 = time.time()

    finally:

        sock.close()

    if len(data) < 48:
        raise RuntimeError(
            "Response NTP tidak valid."
        )

    # Receive Timestamp server
    t2_sec, t2_frac = struct.unpack(
        "!II",
        data[32:40]
    )

    # Transmit Timestamp server
    t3_sec, t3_frac = struct.unpack(
        "!II",
        data[40:48]
    )

    t2 = (
        (t2_sec - NTP_EPOCH)
        + t2_frac / 2**32
    )

    t3 = (
        (t3_sec - NTP_EPOCH)
        + t3_frac / 2**32
    )

    offset_sec = (
        ((t2 - t1) + (t3 - t4))
        / 2
    )

    delay_sec = (
        (t4 - t1)
        - (t3 - t2)
    )

    return (
        offset_sec * 1000,
        delay_sec * 1000
    )


def synchronize_clock():
    """
    Mengambil beberapa sample NTP dan memilih sample
    dengan RTT terendah.
    """

    samples = []

    print()
    print("=" * 70)
    print("SINKRONISASI CLOCK PC")
    print("=" * 70)
    print(f"NTP server : {NTP_SERVER}")
    print()

    for i in range(NTP_SAMPLES):

        try:

            offset, rtt = query_ntp()

            samples.append(
                (offset, rtt)
            )

            print(
                f"Sample {i+1}: "
                f"offset={offset:+.3f} ms | "
                f"RTT={rtt:.3f} ms"
            )

        except Exception as exc:

            print(
                f"Sample {i+1}: gagal | "
                f"{type(exc).__name__}: {exc}"
            )

    if not samples:

        print()
        print(
            "⚠️ NTP tidak berhasil. "
            "Menggunakan clock PC tanpa koreksi."
        )

        print("=" * 70)

        return 0.0, None

    best_offset, best_rtt = min(
        samples,
        key=lambda x: x[1]
    )

    print()
    print(
        f"Offset digunakan : {best_offset:+.3f} ms"
    )

    print(
        f"RTT terbaik       : {best_rtt:.3f} ms"
    )

    print("=" * 70)

    return best_offset, best_rtt


# ============================================================
# CSV
# ============================================================

def open_csv():

    global csv_file
    global csv_writer

    exists = os.path.exists(
        CSV_LOG_FILE
    )

    csv_file = open(
        CSV_LOG_FILE,
        "a",
        newline="",
        encoding="utf-8"
    )

    csv_writer = csv.writer(
        csv_file
    )

    if (
        not exists
        or os.path.getsize(CSV_LOG_FILE) == 0
    ):

        csv_writer.writerow([
            "sequence",

            "device_timestamp_ms",
            "device_timestamp_utc",

            "receive_pc_raw_ms",
            "receive_pc_raw_utc",

            "receive_pc_corrected_ms",
            "receive_pc_corrected_utc",

            "ntp_offset_ms",
            "ntp_rtt_ms",

            "latency_raw_ms",
            "latency_corrected_ms",

            "mqtt_payload_bytes",

            "base64_chars",

            "jpeg_bytes",

            "base64_decode_ms",

            "image_save_ms",

            "voltage_v",
            "current_ma",
            "power_mw",

            "save_image",

            "file_path"
        ])

        csv_file.flush()


def write_csv(
    sequence,
    device_timestamp,
    receive_raw,
    receive_corrected,
    latency_raw,
    latency_corrected,
    payload_bytes,
    base64_chars,
    jpeg_bytes,
    decode_ms,
    save_ms,
    voltage_v,
    current_ma,
    power_mw,
    save_image,
    file_path
):

    csv_writer.writerow([
        sequence,

        device_timestamp,
        iso_from_epoch_ms(
            device_timestamp
        ),

        f"{receive_raw:.3f}",
        iso_from_epoch_ms(
            receive_raw
        ),

        f"{receive_corrected:.3f}",
        iso_from_epoch_ms(
            receive_corrected
        ),

        f"{ntp_offset_ms:.3f}",

        ""
        if ntp_rtt_ms is None
        else f"{ntp_rtt_ms:.3f}",

        f"{latency_raw:.3f}",
        f"{latency_corrected:.3f}",

        payload_bytes,

        base64_chars,

        jpeg_bytes,

        f"{decode_ms:.3f}",

        ""
        if save_ms is None
        else f"{save_ms:.3f}",

        ""
        if voltage_v is None
        else voltage_v,

        ""
        if current_ma is None
        else current_ma,

        ""
        if power_mw is None
        else power_mw,

        int(save_image),

        ""
        if file_path is None
        else file_path
    ])

    csv_file.flush()


# ============================================================
# IMAGE SAVE
# ============================================================

def save_jpeg(image_bytes, sequence):

    os.makedirs(
        IMAGE_DIR,
        exist_ok=True
    )

    filename = (
        f"frame_{sequence:06d}.jpg"
    )

    path = Path(
        IMAGE_DIR
    ) / filename

    with open(
        path,
        "wb"
    ) as f:

        f.write(
            image_bytes
        )

    return str(path)


# ============================================================
# STATISTICS
# ============================================================

def percentile(values, p):

    if not values:
        return 0.0

    values = sorted(values)

    if len(values) == 1:
        return float(values[0])

    k = (
        len(values) - 1
    ) * p

    low = int(k)

    high = min(
        low + 1,
        len(values) - 1
    )

    if low == high:
        return float(
            values[low]
        )

    return (
        values[low]
        + (
            values[high]
            - values[low]
        )
        * (k - low)
    )


def print_statistics():

    if not latencies_corrected:

        print(
            "[STAT] Belum ada data valid."
        )

        return

    print()
    print("=" * 70)
    print("STATISTIK LATENCY")
    print("=" * 70)

    print(
        f"Valid message : {valid_count}"
    )

    print(
        f"Invalid       : {invalid_count}"
    )

    print()

    print("Latency RAW:")
    print(
        f"  Mean   : "
        f"{statistics.mean(latencies_raw):.3f} ms"
    )

    print(
        f"  Median : "
        f"{statistics.median(latencies_raw):.3f} ms"
    )

    print(
        f"  P95    : "
        f"{percentile(latencies_raw, 0.95):.3f} ms"
    )

    print(
        f"  Max    : "
        f"{max(latencies_raw):.3f} ms"
    )

    print()

    print("Latency CORRECTED:")
    print(
        f"  Mean   : "
        f"{statistics.mean(latencies_corrected):.3f} ms"
    )

    print(
        f"  Median : "
        f"{statistics.median(latencies_corrected):.3f} ms"
    )

    print(
        f"  P95    : "
        f"{percentile(latencies_corrected, 0.95):.3f} ms"
    )

    print(
        f"  Max    : "
        f"{max(latencies_corrected):.3f} ms"
    )

    print()

    print("Payload:")
    print(
        f"  Mean MQTT payload : "
        f"{statistics.mean(payload_sizes):.1f} bytes"
    )

    print(
        f"  Mean JPEG size   : "
        f"{statistics.mean(jpeg_sizes):.1f} bytes"
    )

    print()

    print("Base64 decode di subscriber:")
    print(
        f"  Mean : "
        f"{statistics.mean(base64_decode_times):.3f} ms"
    )

    print(
        f"  Max  : "
        f"{max(base64_decode_times):.3f} ms"
    )

    if image_save_times:

        print()

        print("Save image:")
        print(
            f"  Mean : "
            f"{statistics.mean(image_save_times):.3f} ms"
        )

        print(
            f"  Max  : "
            f"{max(image_save_times):.3f} ms"
        )

    if power_values_mw:

        print()

        print("Data daya:")
        print(
            f"  Voltage mean : "
            f"{statistics.mean(voltage_values):.3f} V"
        )

        print(
            f"  Current mean : "
            f"{statistics.mean(current_values_ma):.3f} mA"
        )

        print(
            f"  Power mean   : "
            f"{statistics.mean(power_values_mw):.3f} mW"
        )

        print(
            f"  Power min    : "
            f"{min(power_values_mw):.3f} mW"
        )

        print(
            f"  Power max    : "
            f"{max(power_values_mw):.3f} mW"
        )

    print("=" * 70)


# ============================================================
# MQTT
# ============================================================

def on_connect(client, userdata, flags, rc):

    print(
        f"[MQTT] Connected | rc={rc}"
    )

    if rc == 0:

        result, mid = client.subscribe(
            MQTT_TOPIC,
            qos=0
        )

        print(
            "[MQTT] Subscribe | "
            f"topic={MQTT_TOPIC} | "
            f"result={result} | "
            f"mid={mid}"
        )


def on_subscribe(client, userdata, mid, granted_qos):

    print(
        "[MQTT] Subscription berhasil | "
        f"mid={mid} | qos={granted_qos}"
    )


def on_disconnect(client, userdata, rc):

    print(
        "[MQTT] Disconnected | "
        f"rc={rc}"
    )


def on_message(client, userdata, msg):

    global message_count
    global valid_count
    global invalid_count

    # ========================================================
    # T_RECEIVE
    # ========================================================
    # HARUS diambil sebelum:
    # - JSON parsing
    # - Base64 decoding
    # - file save
    #
    # Jadi pekerjaan subscriber tidak ikut membuat latency
    # terlihat lebih tinggi.
    # ========================================================

    receive_pc_raw_ms = epoch_ms()

    message_count += 1

    payload = msg.payload

    payload_size = len(
        payload
    )

    try:

        # ----------------------------------------------------
        # JSON
        # ----------------------------------------------------

        data = json.loads(
            payload.decode(
                "utf-8"
            )
        )


        # ----------------------------------------------------
        # Device timestamp
        # ----------------------------------------------------

        device_timestamp_ms = int(
            data["timestamp"]
        )


        # ----------------------------------------------------
        # Raw latency
        # ----------------------------------------------------

        latency_raw_ms = (
            receive_pc_raw_ms
            - device_timestamp_ms
        )


        # ----------------------------------------------------
        # Corrected PC time
        # ----------------------------------------------------

        receive_pc_corrected_ms = (
            receive_pc_raw_ms
            + ntp_offset_ms
        )


        latency_corrected_ms = (
            receive_pc_corrected_ms
            - device_timestamp_ms
        )


        # ----------------------------------------------------
        # Basic clock validation
        # ----------------------------------------------------

        if latency_corrected_ms < -1000:

            invalid_count += 1

            print()
            print(
                "[WARNING] Timestamp masih "
                "tidak sinkron!"
            )

            print(
                f"ESP32 : {device_timestamp_ms}"
            )

            print(
                f"PC raw: {receive_pc_raw_ms:.3f}"
            )

            print(
                f"offset: {ntp_offset_ms:+.3f}"
            )

            print(
                f"latency corrected: "
                f"{latency_corrected_ms:.3f} ms"
            )

            return


        # ----------------------------------------------------
        # Base64
        # ----------------------------------------------------

        image_b64 = data.get(
            "image",
            ""
        )

        if not image_b64:

            invalid_count += 1

            print(
                "[WARNING] Field image kosong."
            )

            return


        # ----------------------------------------------------
        # Base64 -> JPEG
        # ----------------------------------------------------

        decode_start = (
            time.perf_counter()
        )

        image_bytes = (
            base64.b64decode(
                image_b64,
                validate=True
            )
        )

        decode_ms = (
            time.perf_counter()
            - decode_start
        ) * 1000


        if not image_bytes:

            invalid_count += 1

            print(
                "[WARNING] JPEG kosong."
            )

            return


        jpeg_size = len(
            image_bytes
        )


        # ----------------------------------------------------
        # Save JPEG
        # ----------------------------------------------------

        save_ms = None
        file_path = None

        if SAVE_IMAGES:

            save_start = (
                time.perf_counter()
            )

            file_path = save_jpeg(
                image_bytes,
                message_count
            )

            save_ms = (
                time.perf_counter()
                - save_start
            ) * 1000

            image_save_times.append(
                save_ms
            )


        # ----------------------------------------------------
        # DATA DAYA
        # ----------------------------------------------------
        # Publisher saat ini memakai:
        #   voltage_v  -> Volt
        #   current_ma -> milliampere
        #   power_mw   -> milliwatt
        #
        # Simpan juga ke CSV supaya hasil latency dan daya
        # bisa dianalisis dalam eksperimen yang sama.
        # ----------------------------------------------------

        voltage_v = data.get("voltage_v")
        current_ma = data.get("current_ma")
        power_mw = data.get("power_mw")

        # Backward compatibility bila payload lama masih digunakan.
        if voltage_v is None:
            voltage_v = data.get("voltage")

        if current_ma is None:
            current_ma = data.get("current_ma")

        if current_ma is None:
            current_a = data.get("current_a")
            if current_a is not None:
                current_ma = float(current_a) * 1000.0

        if power_mw is None:
            power_mw = data.get("power_mw")

        if power_mw is None:
            power_w = data.get("power_w")
            if power_w is not None:
                power_mw = float(power_w) * 1000.0


        # ----------------------------------------------------
        # Store stats
        # ----------------------------------------------------

        valid_count += 1

        latencies_raw.append(
            float(latency_raw_ms)
        )

        latencies_corrected.append(
            float(latency_corrected_ms)
        )

        payload_sizes.append(
            payload_size
        )

        jpeg_sizes.append(
            jpeg_size
        )

        base64_decode_times.append(
            decode_ms
        )

        if voltage_v is not None:
            voltage_values.append(
                float(voltage_v)
            )

        if current_ma is not None:
            current_values_ma.append(
                float(current_ma)
            )

        if power_mw is not None:
            power_values_mw.append(
                float(power_mw)
            )


        # ----------------------------------------------------
        # CSV
        # ----------------------------------------------------

        write_csv(
            sequence=message_count,

            device_timestamp=device_timestamp_ms,

            receive_raw=receive_pc_raw_ms,

            receive_corrected=receive_pc_corrected_ms,

            latency_raw=latency_raw_ms,

            latency_corrected=latency_corrected_ms,

            payload_bytes=payload_size,

            base64_chars=len(
                image_b64
            ),

            jpeg_bytes=jpeg_size,

            decode_ms=decode_ms,

            save_ms=save_ms,

            voltage_v=voltage_v,

            current_ma=current_ma,

            power_mw=power_mw,

            save_image=SAVE_IMAGES,

            file_path=file_path
        )


        # ----------------------------------------------------
        # Display
        # ----------------------------------------------------

        print(
            f"[{message_count:06d}] "
            f"lat={latency_corrected_ms:8.3f} ms | "
            f"payload={payload_size:7d} B | "
            f"jpeg={jpeg_size:7d} B | "
            f"b64decode={decode_ms:6.3f} ms | "
            f"power={power_mw if power_mw is not None else '-'} mW"
        )


        if file_path:

            print(
                f"           saved={file_path}"
            )


        if (
            PRINT_EVERY > 0
            and valid_count % PRINT_EVERY == 0
        ):

            print_statistics()


    except Exception as exc:

        invalid_count += 1

        print()
        print(
            "[MQTT ERROR] Message gagal diproses:"
        )

        print(
            f"  {type(exc).__name__}: {exc}"
        )

        print(
            f"  payload={payload_size} bytes"
        )


# ============================================================
# MQTT CLIENT
# ============================================================

def create_client():

    try:

        client = mqtt.Client(
            callback_api_version=
                mqtt.CallbackAPIVersion.VERSION1
        )

    except (
        AttributeError,
        TypeError
    ):

        client = mqtt.Client()


    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    return client


# ============================================================
# MAIN
# ============================================================

def main():

    global ntp_offset_ms
    global ntp_rtt_ms
    global csv_file

    # --------------------------------------------------------
    # NTP
    # --------------------------------------------------------

    (
        ntp_offset_ms,
        ntp_rtt_ms
    ) = synchronize_clock()


    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    open_csv()


    # --------------------------------------------------------
    # MQTT
    # --------------------------------------------------------

    client = create_client()


    print()
    print("=" * 70)
    print("MQTT IMAGE + LATENCY TEST")
    print("=" * 70)

    print(
        f"Broker       : "
        f"{MQTT_BROKER}:{MQTT_PORT}"
    )

    print(
        f"Topic        : "
        f"{MQTT_TOPIC}"
    )

    print(
        f"CSV          : "
        f"{os.path.abspath(CSV_LOG_FILE)}"
    )

    print(
        f"Image folder : "
        f"{os.path.abspath(IMAGE_DIR)}"
    )

    print(
        f"Save images  : "
        f"{SAVE_IMAGES}"
    )

    print()
    print(
        "Terima message -> ukur timestamp -> "
        "parse/decode -> save image."
    )

    print(
        "Timestamp receive diambil sebelum "
        "Base64 decode dan file save."
    )

    print()
    print(
        "Ctrl+C untuk menghentikan test."
    )

    print("=" * 70)


    try:

        client.connect(
            MQTT_BROKER,
            MQTT_PORT,
            MQTT_KEEPALIVE
        )

        client.loop_forever()


    except KeyboardInterrupt:

        print()
        print(
            "[INFO] Test dihentikan."
        )


    except Exception as exc:

        print()
        print(
            "[FATAL]",
            type(exc).__name__,
            exc
        )


    finally:

        print_statistics()

        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    main()