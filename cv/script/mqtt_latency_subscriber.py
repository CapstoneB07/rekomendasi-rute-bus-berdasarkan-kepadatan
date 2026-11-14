"""Uji latensi publisher KodeWifi_KirimGambardanTimestamp (1).ino.

Payload: {"timestamp": <Unix epoch ms>, "image": "<Base64 JPEG>"}.
Timestamp ESP32 diambil setelah esp_camera_fb_get(), sebelum encoding dan publish.
Latensi mencakup encoding, antrean/reconnect publisher, broker, jaringan, dan waktu
sampai callback PC; tidak mengukur durasi capture atau latency jaringan saja.
Clock PC dikoreksi secara lokal terhadap NTP, tanpa mengubah jam sistem.
Offset WIB pada configTime() tidak ditambahkan lagi ke Unix epoch.

CSV baru dibuat per sesi di outputs/telemetry/. Baris invalid tetap dicatat.
Jalankan --help untuk opsi. Dependency jaringan: pip install paho-mqtt.
"""

import argparse
import base64
import binascii
import csv
import json
import socket
import statistics
import struct
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cv_paths import OUTPUTS_DIR

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "capstone/stefany/esp32s3/camera/base64"
MQTT_KEEPALIVE = 60
NTP_SERVER = "pool.ntp.org"
NTP_TIMEOUT_SEC = 3
NTP_SAMPLES = 5
DEFAULT_OUTPUT_DIR = OUTPUTS_DIR / "telemetry"
NTP_EPOCH = 2208988800
CSV_FIELDS = [
    "sequence", "device_timestamp_ms", "device_timestamp_utc",
    "receive_pc_raw_ms", "receive_pc_raw_utc", "receive_pc_corrected_ms",
    "receive_pc_corrected_utc", "ntp_synced", "ntp_offset_ms", "ntp_rtt_ms",
    "ntp_sample_utc", "latency_raw_ms", "latency_corrected_ms",
    "measurement_valid", "status", "error", "mqtt_topic", "mqtt_qos",
    "mqtt_retain", "mqtt_dup", "mqtt_payload_bytes", "base64_chars",
    "jpeg_bytes", "json_parse_ms", "base64_decode_ms", "image_save_ms",
    "save_image", "file_path",
]


def epoch_ms():
    return time.time_ns() / 1_000_000


def iso_from_epoch_ms(value):
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class ClockSync:
    offset_ms: float = 0.0
    rtt_ms: float | None = None
    sample_utc: str = ""

    @property
    def synced(self):
        return self.rtt_ms is not None


def query_ntp(server=NTP_SERVER, timeout=NTP_TIMEOUT_SEC):
    """Estimasi offset dengan empat timestamp NTP; validasi respons server."""
    address = socket.gethostbyname(server)
    packet = bytearray(48)
    packet[0] = 0x23  # NTPv4, mode client.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((address, 123))
        t1 = time.time()
        seconds = int(t1)
        struct.pack_into("!II", packet, 40, seconds + NTP_EPOCH, int((t1 - seconds) * 2**32))
        sock.send(packet)
        response = sock.recv(512)
        t4 = time.time()
    if len(response) < 48:
        raise ValueError("Respons NTP terlalu pendek")
    leap, version, mode = response[0] >> 6, (response[0] >> 3) & 7, response[0] & 7
    if leap == 3 or version not in (3, 4) or mode != 4 or not 1 <= response[1] <= 15:
        raise ValueError("Server NTP belum sinkron atau respons tidak valid")
    if response[24:32] != packet[40:48]:
        raise ValueError("Respons NTP tidak cocok dengan request")

    def unpack_timestamp(start):
        sec, frac = struct.unpack_from("!II", response, start)
        if sec == 0:
            raise ValueError("Timestamp server NTP kosong")
        return sec - NTP_EPOCH + frac / 2**32

    t2, t3 = unpack_timestamp(32), unpack_timestamp(40)
    delay = (t4 - t1) - (t3 - t2)
    if t3 < t2 or delay < -0.001:
        raise ValueError("Urutan waktu NTP tidak valid atau clock PC berubah")
    return ((t2 - t1) + (t3 - t4)) * 500, max(0, delay * 1000)


def synchronize_clock(server=NTP_SERVER, samples=NTP_SAMPLES, timeout=NTP_TIMEOUT_SEC):
    best = ClockSync()
    for index in range(samples):
        try:
            offset, rtt = query_ntp(server, timeout)
        except (OSError, ValueError) as exc:
            print(f"[NTP] Sample {index + 1}/{samples} gagal: {exc}")
            continue
        print(f"[NTP] Sample {index + 1}/{samples}: offset={offset:+.3f} ms, RTT={rtt:.3f} ms")
        if best.rtt_ms is None or rtt < best.rtt_ms:
            best = ClockSync(offset, rtt, iso_from_epoch_ms(epoch_ms()))
    if not best.synced:
        print("[NTP] Tanpa koreksi: latency_raw_ms tetap dicatat; latency_corrected_ms dikosongkan.")
    return best


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class LatencyRecorder:
    def __init__(self, csv_path, image_dir=None, print_every=10):
        self.csv_path = Path(csv_path).expanduser().resolve()
        self.image_dir = Path(image_dir) if image_dir is not None else None
        self.print_every = print_every
        self.clock = ClockSync()
        self.count = 0
        self.valid_count = 0
        self.raw_latencies = []
        self.corrected_latencies = []
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        # Mode x mencegah penimpaan atau pencampuran schema log sesi lama.
        self.file = self.csv_path.open("x", newline="", encoding="utf-8-sig")
        self.writer = csv.DictWriter(self.file, fieldnames=CSV_FIELDS)
        self.writer.writeheader()
        self.file.flush()

    def on_message(self, client, userdata, msg):
        # Sebelum parsing, decoding, logging, atau penulisan gambar.
        received = epoch_ms()
        self.record(msg, received)

    def record(self, msg, received):
        self.count += 1
        row = dict.fromkeys(CSV_FIELDS, "")
        row.update(
            sequence=self.count,
            receive_pc_raw_ms=round(received, 3),
            receive_pc_raw_utc=iso_from_epoch_ms(received),
            ntp_synced=int(self.clock.synced),
            ntp_offset_ms=round(self.clock.offset_ms, 3) if self.clock.synced else "",
            ntp_rtt_ms=round(self.clock.rtt_ms, 3) if self.clock.synced else "",
            ntp_sample_utc=self.clock.sample_utc,
            mqtt_topic=msg.topic,
            mqtt_qos=msg.qos,
            mqtt_retain=int(msg.retain),
            mqtt_dup=int(msg.dup),
            mqtt_payload_bytes=len(msg.payload),
            measurement_valid=0,
            save_image=0,
            status="invalid_payload",
        )
        try:
            started = time.perf_counter()
            data = json.loads(msg.payload.decode("utf-8"))
            row["json_parse_ms"] = round((time.perf_counter() - started) * 1000, 3)
            if not isinstance(data, dict):
                raise ValueError("Payload JSON harus berupa object")

            row["status"] = "invalid_timestamp"
            timestamp = data.get("timestamp")
            # Epoch ms 2020-2100: menolak millis(), epoch detik, bool, dan NTP ESP32 gagal.
            if type(timestamp) is not int or not 1577836800000 <= timestamp < 4102444800000:
                raise ValueError("timestamp harus integer Unix epoch milidetik (clock ESP32 sudah sinkron)")
            row["device_timestamp_ms"] = timestamp
            row["device_timestamp_utc"] = iso_from_epoch_ms(timestamp)
            raw_latency = received - timestamp
            row["latency_raw_ms"] = round(raw_latency, 3)
            corrected_latency = None
            if self.clock.synced:
                corrected = received + self.clock.offset_ms
                corrected_latency = corrected - timestamp
                row["receive_pc_corrected_ms"] = round(corrected, 3)
                row["receive_pc_corrected_utc"] = iso_from_epoch_ms(corrected)
                row["latency_corrected_ms"] = round(corrected_latency, 3)

            row["status"] = "invalid_image"
            image_b64 = data.get("image")
            if not isinstance(image_b64, str) or not image_b64:
                raise ValueError("image harus string Base64 JPEG yang tidak kosong")
            row["base64_chars"] = len(image_b64)
            started = time.perf_counter()
            image = base64.b64decode(image_b64, validate=True)
            row["base64_decode_ms"] = round((time.perf_counter() - started) * 1000, 3)
            row["jpeg_bytes"] = len(image)
            # Pemeriksaan marker saja; tidak menambahkan dependency CV untuk uji transport.
            if not (image.startswith(b"\xff\xd8") and image.endswith(b"\xff\xd9")):
                raise ValueError("Hasil decode tidak memiliki marker awal/akhir JPEG")

            if msg.retain:
                row["status"] = "retained"
                row["error"] = "Pesan retained tidak dimasukkan ke statistik live"
            elif corrected_latency is None:
                row["status"] = "ntp_unavailable"
                row["error"] = "Koreksi clock PC tidak tersedia; gunakan latency_raw_ms dengan hati-hati"
            elif corrected_latency < 0:
                row["status"] = "clock_ahead"
                row["error"] = "Timestamp ESP32 mendahului clock PC terkoreksi; nilai negatif dipertahankan"
            else:
                row["status"] = "ok"
                row["measurement_valid"] = 1

            if self.image_dir is not None:
                started = time.perf_counter()
                try:
                    self.image_dir.mkdir(parents=True, exist_ok=True)
                    path = self.image_dir / f"{timestamp}_{self.count:06d}.jpg"
                    with path.open("xb") as image_file:
                        image_file.write(image)
                    row["file_path"] = str(path.resolve())
                    row["save_image"] = 1
                except OSError as exc:
                    row["error"] = (row["error"] + f"; Gagal menyimpan gambar: {exc}").lstrip("; ")
                    if row["status"] == "ok":
                        row["status"] = "image_save_error"
                row["image_save_ms"] = round((time.perf_counter() - started) * 1000, 3)

            if not msg.retain and (corrected_latency is not None and corrected_latency >= 0
                                   or corrected_latency is None and raw_latency >= 0):
                self.raw_latencies.append(raw_latency)
            if row["measurement_valid"]:
                self.valid_count += 1
                self.corrected_latencies.append(corrected_latency)
        except (ValueError, TypeError, UnicodeError, binascii.Error) as exc:
            row["error"] = str(exc)

        # Error I/O CSV sengaja diteruskan agar program tidak tampak merekam saat disk gagal.
        self.writer.writerow(row)
        self.file.flush()
        latency = row["latency_corrected_ms"]
        if latency == "":
            latency = row["latency_raw_ms"]
        print(f"[{self.count:06d}] status={row['status']} | latency={latency} ms | "
              f"payload={row['mqtt_payload_bytes']} B | JPEG={row['jpeg_bytes']} B")
        if row["error"]:
            print(f"           {row['error']}")
        if self.print_every > 0 and self.count % self.print_every == 0:
            self.print_statistics()
        return row

    def print_statistics(self):
        print(f"[STAT] Total={self.count} | valid terkoreksi={self.valid_count}")
        for label, values in (("RAW", self.raw_latencies), ("CORRECTED", self.corrected_latencies)):
            if values:
                print(f"  {label}: n={len(values)} | mean={statistics.mean(values):.3f} ms | "
                      f"median={statistics.median(values):.3f} ms | "
                      f"P95={percentile(values, 0.95):.3f} ms | max={max(values):.3f} ms")

    def close(self):
        self.file.close()


def create_client(recorder, topic=MQTT_TOPIC):
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise RuntimeError("Dependency belum tersedia. Jalankan: python -m pip install paho-mqtt") from exc

    def on_connect(client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            raise ConnectionError(f"Broker menolak koneksi MQTT: {reason_code}")
        result, _ = client.subscribe(topic, qos=0)
        if result != 0:
            raise ConnectionError(f"Subscribe gagal: {result}")
        print(f"[MQTT] Terhubung; meminta subscribe {topic}")

    def on_subscribe(client, userdata, mid, reason_codes, properties=None):
        if any(getattr(code, "is_failure", False) or getattr(code, "value", code) >= 128
               for code in reason_codes):
            raise ConnectionError(f"Broker menolak subscribe: {reason_codes}")
        print(f"[MQTT] Subscribe berhasil: {topic}; menunggu gambar, Ctrl+C untuk keluar.")

    def on_disconnect(client, userdata, flags_or_rc, reason_code=None, properties=None):
        code = flags_or_rc if reason_code is None else reason_code
        print(f"[MQTT] Terputus: {code}")

    kwargs = {"client_id": f"camera-latency-{uuid.uuid4().hex[:12]}"}
    if hasattr(mqtt, "CallbackAPIVersion"):
        kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
    client = mqtt.Client(**kwargs)
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    client.on_message = recorder.on_message
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    return client


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--broker", default=MQTT_BROKER)
    parser.add_argument("--port", type=int, default=MQTT_PORT)
    parser.add_argument("--topic", default=MQTT_TOPIC)
    parser.add_argument("--csv", type=Path, help="Path CSV baru; file yang sudah ada tidak ditimpa")
    parser.add_argument("--no-save-images", action="store_true")
    parser.add_argument("--ntp-server", default=NTP_SERVER)
    parser.add_argument("--ntp-samples", type=int, default=NTP_SAMPLES)
    parser.add_argument("--ntp-timeout", type=float, default=NTP_TIMEOUT_SEC)
    parser.add_argument("--skip-ntp", action="store_true", help="Hanya catat latensi raw tanpa koreksi")
    parser.add_argument("--print-every", type=int, default=10)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or args.ntp_samples < 1 or args.ntp_timeout <= 0 or args.print_every < 0:
        parser.error("port harus 1..65535; ntp-samples/ntp-timeout > 0; print-every >= 0")
    if not args.topic or "+" in args.topic or "#" in args.topic:
        parser.error("topic harus satu topik publisher tanpa wildcard")
    return args


def main(argv=None):
    args = parse_args(argv)
    session = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]
    csv_path = args.csv or DEFAULT_OUTPUT_DIR / f"mqtt_camera_latency_{session}.csv"
    image_dir = None if args.no_save_images else DEFAULT_OUTPUT_DIR / "received_images_latency" / session
    recorder = None
    client = None
    try:
        # CSV sudah tersedia (beserta header) sebelum sinkronisasi dan koneksi.
        recorder = LatencyRecorder(csv_path, image_dir, args.print_every)
        print(f"CSV: {recorder.csv_path}")
        print(f"Broker: {args.broker}:{args.port} | Topic: {args.topic}")
        print("Latensi: timestamp setelah capture ESP32 sampai callback PC; tanpa tambahan offset WIB.")
        if image_dir is not None:
            print(f"JPEG: {image_dir}")
        if not args.skip_ntp:
            recorder.clock = synchronize_clock(args.ntp_server, args.ntp_samples, args.ntp_timeout)
        client = create_client(recorder, args.topic)
        client.connect(args.broker, args.port, MQTT_KEEPALIVE)
        client.loop_forever(timeout=1.0)
    except KeyboardInterrupt:
        print("\n[INFO] Pengujian dihentikan pengguna.")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    finally:
        try:
            if client is not None:
                client.disconnect()
        finally:
            if recorder is not None:
                recorder.close()
                recorder.print_statistics()
                print(f"CSV tersimpan: {recorder.csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
