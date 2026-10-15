"""
MQTT Subscriber - INA226 Power Test
===================================

Kompatibel dengan publisher ESP32-S3 + INA226 pada topic:

    esp32s3/ina226/data

Payload publisher saat ini:
    {
        "bus_voltage": ...,
        "shunt_voltage": ...,
        "current_mA": ...,
        "power_mW": ...
    }

Fungsi program:
    1. Menerima data INA226 melalui MQTT.
    2. Menampilkan tegangan, tegangan shunt, arus, dan daya.
    3. Menyimpan setiap pembacaan ke CSV.
    4. Menghitung statistik daya, arus, dan tegangan.
    5. Mencatat inter-arrival time antar pesan.

Dukungan timestamp:
    Jika publisher di masa depan menambahkan:
        "timestamp_ms": <Unix Epoch milliseconds>

    maka subscriber otomatis menghitung one-way latency.
    Untuk publisher saat ini, latency akan bernilai N/A karena
    timestamp ESP32 belum dikirim.

CSV output:
    mqtt_ina226_power_log.csv
"""

import csv
import json
import os
import statistics
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


# ============================================================
# KONFIGURASI MQTT
# ============================================================

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "esp32s3/ina226/data"
MQTT_KEEPALIVE = 60


# ============================================================
# KONFIGURASI OUTPUT
# ============================================================

CSV_LOG_FILE = "mqtt_ina226_power_log.csv"

# Tampilkan statistik setiap N message.
# Set 0 untuk menonaktifkan statistik berkala.
PRINT_EVERY = 10


# ============================================================
# STATISTIK
# ============================================================

message_count = 0
valid_power_count = 0
invalid_count = 0

power_values_mw = []
current_values_ma = []
voltage_values_v = []
inter_arrival_values_ms = []
latency_values_ms = []

last_receive_ms = None

csv_file = None
csv_writer = None


# ============================================================
# UTILITY: TIME
# ============================================================

def epoch_ms():
    """Mengembalikan Unix Epoch dalam milidetik dari PC."""
    return time.time_ns() / 1_000_000.0


def iso_from_epoch_ms(value_ms):
    """Mengubah Unix Epoch ms menjadi ISO-8601 UTC."""
    dt = datetime.fromtimestamp(
        value_ms / 1000.0,
        tz=timezone.utc
    )
    return dt.isoformat(timespec="milliseconds")


# ============================================================
# CSV
# ============================================================

def open_csv():
    """Membuka CSV dan membuat header jika file masih kosong."""
    global csv_file, csv_writer

    exists = os.path.exists(CSV_LOG_FILE)

    csv_file = open(
        CSV_LOG_FILE,
        "a",
        newline="",
        encoding="utf-8"
    )

    csv_writer = csv.writer(csv_file)

    if not exists or os.path.getsize(CSV_LOG_FILE) == 0:
        csv_writer.writerow([
            "sequence",
            "receive_pc_ms",
            "receive_pc_utc",
            "device_timestamp_ms",
            "device_timestamp_utc",
            "latency_ms",
            "inter_arrival_ms",
            "bus_voltage_v",
            "shunt_voltage_mv",
            "current_ma",
            "power_mw"
        ])
        csv_file.flush()


def write_csv(
    sequence,
    receive_ms,
    device_timestamp_ms,
    latency_ms,
    inter_arrival_ms,
    bus_voltage,
    shunt_voltage,
    current_ma,
    power_mw
):
    """Menulis satu pembacaan ke CSV."""
    csv_writer.writerow([
        sequence,
        f"{receive_ms:.3f}",
        iso_from_epoch_ms(receive_ms),

        ""
        if device_timestamp_ms is None
        else f"{device_timestamp_ms:.0f}",

        ""
        if device_timestamp_ms is None
        else iso_from_epoch_ms(device_timestamp_ms),

        ""
        if latency_ms is None
        else f"{latency_ms:.3f}",

        ""
        if inter_arrival_ms is None
        else f"{inter_arrival_ms:.3f}",

        ""
        if bus_voltage is None
        else f"{float(bus_voltage):.3f}",

        ""
        if shunt_voltage is None
        else f"{float(shunt_voltage):.3f}",

        ""
        if current_ma is None
        else f"{float(current_ma):.3f}",

        ""
        if power_mw is None
        else f"{float(power_mw):.3f}"
    ])

    csv_file.flush()


# ============================================================
# STATISTIK
# ============================================================

def percentile(values, p):
    """Percentile sederhana dengan interpolasi linear."""
    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return float(ordered[0])

    position = (len(ordered) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)

    if lower == upper:
        return float(ordered[lower])

    fraction = position - lower

    return (
        ordered[lower]
        + (ordered[upper] - ordered[lower]) * fraction
    )


def print_statistics():
    """Menampilkan ringkasan hasil pengukuran."""
    print()
    print("=" * 70)
    print("STATISTIK MQTT INA226")
    print("=" * 70)

    print(f"Message diterima : {message_count}")
    print(f"Data power valid : {valid_power_count}")
    print(f"Invalid          : {invalid_count}")

    if power_values_mw:
        print()
        print("DAYA")
        print(f"  Mean : {statistics.mean(power_values_mw):.3f} mW")
        print(f"  Min  : {min(power_values_mw):.3f} mW")
        print(f"  Max  : {max(power_values_mw):.3f} mW")

    if current_values_ma:
        print()
        print("ARUS")
        print(f"  Mean : {statistics.mean(current_values_ma):.3f} mA")
        print(f"  Min  : {min(current_values_ma):.3f} mA")
        print(f"  Max  : {max(current_values_ma):.3f} mA")

    if voltage_values_v:
        print()
        print("TEGANGAN BUS")
        print(f"  Mean : {statistics.mean(voltage_values_v):.3f} V")
        print(f"  Min  : {min(voltage_values_v):.3f} V")
        print(f"  Max  : {max(voltage_values_v):.3f} V")

    if inter_arrival_values_ms:
        print()
        print("INTER-ARRIVAL TIME")
        print(
            f"  Mean   : "
            f"{statistics.mean(inter_arrival_values_ms):.3f} ms"
        )
        print(
            f"  Median : "
            f"{statistics.median(inter_arrival_values_ms):.3f} ms"
        )
        print(
            f"  Min    : "
            f"{min(inter_arrival_values_ms):.3f} ms"
        )
        print(
            f"  Max    : "
            f"{max(inter_arrival_values_ms):.3f} ms"
        )

    if latency_values_ms:
        print()
        print("ONE-WAY LATENCY")
        print(
            f"  Mean   : "
            f"{statistics.mean(latency_values_ms):.3f} ms"
        )
        print(
            f"  Median : "
            f"{statistics.median(latency_values_ms):.3f} ms"
        )
        print(
            f"  P95    : "
            f"{percentile(latency_values_ms, 0.95):.3f} ms"
        )
        print(
            f"  Min    : "
            f"{min(latency_values_ms):.3f} ms"
        )
        print(
            f"  Max    : "
            f"{max(latency_values_ms):.3f} ms"
        )

    print("=" * 70)


# ============================================================
# MQTT CALLBACKS
# ============================================================

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected | rc={rc}")

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
    print(f"[MQTT] Disconnected | rc={rc}")


def on_message(client, userdata, msg):
    global message_count
    global valid_power_count
    global invalid_count
    global last_receive_ms

    # Ambil waktu penerimaan sesegera mungkin.
    receive_ms = epoch_ms()

    message_count += 1

    payload_size = len(msg.payload)

    # --------------------------------------------------------
    # INTER-ARRIVAL TIME
    # --------------------------------------------------------

    inter_arrival_ms = None

    if last_receive_ms is not None:
        inter_arrival_ms = receive_ms - last_receive_ms
        inter_arrival_values_ms.append(inter_arrival_ms)

    last_receive_ms = receive_ms

    try:
        # ----------------------------------------------------
        # PARSE JSON
        # ----------------------------------------------------

        data = json.loads(
            msg.payload.decode("utf-8")
        )

        # ----------------------------------------------------
        # DATA INA226
        # ----------------------------------------------------

        bus_voltage = data.get("bus_voltage")
        shunt_voltage = data.get("shunt_voltage")
        current_ma = data.get("current_mA")
        power_mw = data.get("power_mW")

        # ----------------------------------------------------
        # OPTIONAL TIMESTAMP
        # ----------------------------------------------------

        device_timestamp = data.get("timestamp_ms")

        if device_timestamp is None:
            device_timestamp = data.get("timestamp")

        latency_ms = None

        if device_timestamp is not None:
            device_timestamp = float(device_timestamp)

            latency_ms = (
                receive_ms
                - device_timestamp
            )

            # Nilai negatif besar menandakan kemungkinan
            # clock ESP32 dan PC tidak sinkron.
            if latency_ms < -1000:
                print(
                    "[WARNING] Timestamp tidak sinkron | "
                    f"latency={latency_ms:.3f} ms"
                )
                latency_ms = None
            else:
                latency_values_ms.append(latency_ms)

        # ----------------------------------------------------
        # VALIDASI DATA POWER
        # ----------------------------------------------------

        required_fields = (
            bus_voltage,
            shunt_voltage,
            current_ma,
            power_mw
        )

        if any(value is None for value in required_fields):
            invalid_count += 1

            print(
                f"[{message_count:06d}] "
                "Payload tidak lengkap | "
                f"payload={payload_size} B"
            )

            return

        valid_power_count += 1

        power_values_mw.append(
            float(power_mw)
        )

        current_values_ma.append(
            float(current_ma)
        )

        voltage_values_v.append(
            float(bus_voltage)
        )

        # ----------------------------------------------------
        # CSV
        # ----------------------------------------------------

        write_csv(
            sequence=message_count,
            receive_ms=receive_ms,
            device_timestamp_ms=device_timestamp,
            latency_ms=latency_ms,
            inter_arrival_ms=inter_arrival_ms,
            bus_voltage=bus_voltage,
            shunt_voltage=shunt_voltage,
            current_ma=current_ma,
            power_mw=power_mw
        )

        # ----------------------------------------------------
        # CONSOLE
        # ----------------------------------------------------

        latency_text = (
            f"{latency_ms:.3f} ms"
            if latency_ms is not None
            else "N/A"
        )

        inter_arrival_text = (
            f"{inter_arrival_ms:.3f} ms"
            if inter_arrival_ms is not None
            else "N/A"
        )

        print(
            f"[{message_count:06d}] "
            f"V={float(bus_voltage):.3f} V | "
            f"Vshunt={float(shunt_voltage):.3f} mV | "
            f"I={float(current_ma):.3f} mA | "
            f"P={float(power_mw):.3f} mW | "
            f"Latency={latency_text} | "
            f"Interval={inter_arrival_text}"
        )

        if (
            PRINT_EVERY > 0
            and message_count % PRINT_EVERY == 0
        ):
            print_statistics()

    except Exception as exc:
        invalid_count += 1

        print()
        print(
            "[MQTT ERROR] Gagal memproses message | "
            f"{type(exc).__name__}: {exc}"
        )
        print(
            f"Payload size: {payload_size} bytes"
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
    except (AttributeError, TypeError):
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
    global csv_file

    open_csv()

    client = create_client()

    print()
    print("=" * 70)
    print("MQTT INA226 POWER SUBSCRIBER")
    print("=" * 70)
    print(f"Broker : {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Topic  : {MQTT_TOPIC}")
    print(f"CSV    : {os.path.abspath(CSV_LOG_FILE)}")
    print()
    print("Payload yang diharapkan:")
    print("  bus_voltage")
    print("  shunt_voltage")
    print("  current_mA")
    print("  power_mW")
    print()
    print(
        "Timestamp bersifat opsional. "
        "Publisher saat ini belum mengirim timestamp."
    )
    print(
        "Inter-arrival time tetap dicatat."
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
        print("\n[INFO] Subscriber dihentikan.")

    except Exception as exc:
        print(
            f"\n[FATAL] {type(exc).__name__}: {exc}"
        )

    finally:
        print_statistics()

        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    main()
