"""Pengujian offline: python -m unittest discover -s cv/script -p test_mqtt_latency_subscriber.py."""

import base64
import contextlib
import csv
import io
import json
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import mqtt_latency_subscriber as subscriber


EPOCH_MS = 1793270000000
JPEG = b"\xff\xd8\xff\xe0test-jpeg\xff\xd9"


def message(payload=None, **overrides):
    if payload is None:
        payload = {"timestamp": EPOCH_MS, "image": base64.b64encode(JPEG).decode("ascii")}
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    values = dict(payload=raw, topic=subscriber.MQTT_TOPIC, qos=0, retain=False, dup=False)
    values.update(overrides)
    return types.SimpleNamespace(**values)


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.csv_path = Path(self.temp.name) / "session.csv"
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.recorder = subscriber.LatencyRecorder(self.csv_path, print_every=0)
        self.addCleanup(self.recorder.close)
        self.recorder.clock = subscriber.ClockSync(25, 8, "2026-10-29T00:00:00+00:00")

    def read_rows(self):
        # File masih terbuka di recorder: membuktikan flush per pesan.
        with self.csv_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            self.assertEqual(reader.fieldnames, subscriber.CSV_FIELDS)
            rows = list(reader)
        self.assertTrue(all(None not in row for row in rows))
        return rows

    def test_publisher_payload_and_latency_csv(self):
        row = self.recorder.record(message(), EPOCH_MS + 100)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["latency_raw_ms"], 100)
        self.assertEqual(row["latency_corrected_ms"], 125)
        self.assertEqual(row["measurement_valid"], 1)
        self.assertEqual(row["jpeg_bytes"], len(JPEG))
        saved = self.read_rows()[0]
        self.assertEqual(saved["latency_corrected_ms"], "125")
        self.assertEqual(saved["mqtt_topic"], "capstone/stefany/esp32s3/camera/base64")

    def test_invalid_messages_logged_and_next_message_still_works(self):
        cases = [
            (b"not-json", "invalid_payload"),
            (b"\xff", "invalid_payload"),
            ([], "invalid_payload"),
            ({"image": "abc"}, "invalid_timestamp"),
            ({"timestamp": True, "image": "abc"}, "invalid_timestamp"),
            ({"timestamp": EPOCH_MS // 1000, "image": "abc"}, "invalid_timestamp"),
            ({"timestamp": 1000, "image": "abc"}, "invalid_timestamp"),
            ({"timestamp": EPOCH_MS}, "invalid_image"),
            ({"timestamp": EPOCH_MS, "image": "!not-base64!"}, "invalid_image"),
            ({"timestamp": EPOCH_MS, "image": base64.b64encode(b"not jpeg").decode()}, "invalid_image"),
        ]
        for payload, status in cases:
            with self.subTest(payload=payload):
                row = self.recorder.record(message(payload), EPOCH_MS + 100)
                self.assertEqual(row["status"], status)
                self.assertEqual(row["measurement_valid"], 0)
                self.assertTrue(row["error"])
        self.recorder.record(message(), EPOCH_MS + 100)
        self.assertEqual(len(self.read_rows()), len(cases) + 1)
        self.assertEqual(self.recorder.valid_count, 1)

    def test_no_ntp_leaves_corrected_latency_blank(self):
        self.recorder.clock = subscriber.ClockSync()
        row = self.recorder.record(message(), EPOCH_MS + 100)
        self.assertEqual(row["status"], "ntp_unavailable")
        self.assertEqual(row["latency_corrected_ms"], "")
        self.assertEqual(row["ntp_offset_ms"], "")
        self.assertEqual(self.recorder.raw_latencies, [100])
        self.assertEqual(self.recorder.corrected_latencies, [])

    def test_negative_and_retained_values_kept_out_of_statistics(self):
        row = self.recorder.record(message(), EPOCH_MS - 100)
        self.assertEqual(row["latency_corrected_ms"], -75)
        self.assertEqual(row["status"], "clock_ahead")
        retained = self.recorder.record(message(retain=True), EPOCH_MS + 100)
        self.assertEqual(retained["status"], "retained")
        self.assertEqual(self.recorder.valid_count, 0)
        self.assertEqual(self.recorder.raw_latencies, [])
        self.assertEqual(len(self.read_rows()), 2)

    def test_image_saved_and_recorded_without_changing_latency(self):
        self.recorder.image_dir = Path(self.temp.name) / "images"
        row = self.recorder.record(message(), EPOCH_MS + 100)
        self.assertEqual(Path(row["file_path"]).read_bytes(), JPEG)
        self.assertEqual(row["save_image"], 1)
        self.assertEqual(row["latency_corrected_ms"], 125)

    def test_image_save_failure_preserves_latency_and_csv(self):
        self.recorder.image_dir = Path(self.temp.name) / "images"
        with patch.object(Path, "mkdir", side_effect=OSError("disk full")):
            row = self.recorder.record(message(), EPOCH_MS + 100)
        self.assertEqual(row["status"], "image_save_error")
        self.assertEqual(row["measurement_valid"], 1)
        self.assertEqual(row["save_image"], 0)
        self.assertIn("disk full", self.read_rows()[0]["error"])

    def test_callback_captures_receive_time_before_processing(self):
        with patch.object(subscriber, "epoch_ms", return_value=EPOCH_MS + 100), \
                patch.object(self.recorder, "record") as record:
            msg = message()
            self.recorder.on_message(None, None, msg)
        record.assert_called_once_with(msg, EPOCH_MS + 100)

    def test_csv_already_exists_is_not_overwritten(self):
        before = self.csv_path.read_bytes()
        with self.assertRaises(FileExistsError):
            subscriber.LatencyRecorder(self.csv_path)
        self.assertEqual(self.csv_path.read_bytes(), before)

    def test_csv_write_failure_is_not_swallowed(self):
        self.recorder.writer = Mock()
        self.recorder.writer.writerow.side_effect = OSError("disk full")
        with self.assertRaises(OSError):
            self.recorder.record(message(), EPOCH_MS + 100)


class ClockTests(unittest.TestCase):
    @staticmethod
    def response(request):
        data = bytearray(48)
        data[0], data[1] = 0x24, 2
        data[24:32] = request[40:48]
        # Local t1=1e9, t4=1e9+0.1; server ahead by 200 ms, RTT 90 ms.
        for start, stamp in ((32, 1000000000.245), (40, 1000000000.255)):
            sec = int(stamp)
            struct.pack_into("!II", data, start, sec + subscriber.NTP_EPOCH, int((stamp - sec) * 2**32))
        return data

    def query_with_response(self, mutate=lambda data: data):
        sock = Mock()
        sock.__enter__ = Mock(return_value=sock)
        sock.__exit__ = Mock(return_value=False)
        sock.recv.side_effect = lambda size: mutate(self.response(sock.send.call_args.args[0]))
        with patch.object(subscriber.socket, "gethostbyname", return_value="127.0.0.1"), \
                patch.object(subscriber.socket, "socket", return_value=sock), \
                patch.object(subscriber.time, "time", side_effect=[1000000000, 1000000000.1]):
            return subscriber.query_ntp()

    def test_four_timestamp_ntp_offset(self):
        offset, rtt = self.query_with_response()
        self.assertAlmostEqual(offset, 200, places=2)
        self.assertAlmostEqual(rtt, 90, places=2)

    def test_invalid_ntp_responses_rejected(self):
        def wrong_origin(data):
            data[24] ^= 1
            return data

        def unsynced(data):
            data[0] |= 0xC0
            return data

        for mutate in (wrong_origin, unsynced, lambda data: data[:20]):
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.query_with_response(mutate)

    def test_best_rtt_selected_and_failure_not_marked_synced(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(subscriber, "query_ntp", side_effect=[OSError(), (20, 10), (30, 5)]):
                clock = subscriber.synchronize_clock(samples=3)
            self.assertEqual(clock.offset_ms, 30)
            with patch.object(subscriber, "query_ntp", side_effect=OSError()):
                self.assertFalse(subscriber.synchronize_clock(samples=1).synced)


class LifecycleTests(unittest.TestCase):
    def test_ctrl_c_during_sync_or_mqtt_closes_csv(self):
        for phase in ("sync", "mqtt"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "log.csv"
                client = Mock()
                client.loop_forever.side_effect = KeyboardInterrupt
                with contextlib.redirect_stdout(io.StringIO()), \
                        patch.object(subscriber, "create_client", return_value=client), \
                        patch.object(subscriber, "synchronize_clock", side_effect=KeyboardInterrupt if phase == "sync" else None,
                                     return_value=subscriber.ClockSync()):
                    self.assertEqual(subscriber.main(["--csv", str(path), "--no-save-images"]), 0)
                # Rename succeeds on Windows only after handle is closed.
                path.rename(Path(temp) / "closed.csv")
                if phase == "mqtt":
                    client.disconnect.assert_called_once()

    def test_connection_failure_returns_error_and_preserves_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "log.csv"
            client = Mock()
            client.connect.side_effect = OSError("offline")
            with contextlib.redirect_stdout(io.StringIO()), patch.object(subscriber, "create_client", return_value=client):
                self.assertEqual(subscriber.main(["--csv", str(path), "--skip-ntp", "--no-save-images"]), 1)
            self.assertTrue(path.is_file())

    def test_paho_v1_and_v2_callbacks(self):
        for version2 in (False, True):
            with self.subTest(version2=version2):
                mqtt = types.ModuleType("paho.mqtt.client")
                mqtt.Client = Mock()
                if version2:
                    mqtt.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
                paho = types.ModuleType("paho")
                package = types.ModuleType("paho.mqtt")
                paho.mqtt, package.client = package, mqtt
                with patch.dict(sys.modules, {"paho": paho, "paho.mqtt": package, "paho.mqtt.client": mqtt}):
                    recorder = Mock()
                    client = subscriber.create_client(recorder)
                    client.subscribe.return_value = (0, 1)
                    client.on_connect(client, None, {}, 0, *([None] if version2 else []))
                    client.subscribe.assert_called_once_with(subscriber.MQTT_TOPIC, qos=0)
                    with self.assertRaises(ConnectionError):
                        client.on_subscribe(client, None, 1, [128], *([None] if version2 else []))
                    if version2:
                        self.assertEqual(mqtt.Client.call_args.kwargs["callback_api_version"], 2)


if __name__ == "__main__":
    unittest.main()
