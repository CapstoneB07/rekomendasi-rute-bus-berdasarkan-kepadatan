"""MQTT camera subscriber: JPEG chunks (GSM) and complete JPEG/Base64 (legacy).

Output to Redis: one complete raw JPEG per queue item.
Compatible with cv/worker/cv_worker.py BRPOP.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import redis
import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "capstone/stefany/esp32s3/camera/base64")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "capstone-cv-subscriber")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
BUS_ID = os.getenv("BUS_ID", "Koridor_1_A")
REDIS_QUEUE_NAME = os.getenv("REDIS_QUEUE_NAME", f"cv_task_queue:{BUS_ID}")

SAVE_RECEIVED_IMAGES = os.getenv("SAVE_RECEIVED_IMAGES", "true").lower() in {"1", "true", "yes"}
SAVE_DIR = Path(os.getenv("SAVE_DIR", "received_images"))

HEADER = struct.Struct("<IHHI")  # frame_id, chunk_index, total_chunks, total_len
CHUNK_SIZE = 512
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_INFLIGHT_FRAMES = 8
FRAME_TIMEOUT_SECONDS = 240.0
RECENT_FRAME_SECONDS = 30.0
LOG = logging.getLogger("capstone.mqtt")
LOG_EVERY = max(1, int(os.getenv("LOG_EVERY", "10")))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()



def is_jpeg(blob: bytes) -> bool:
    """Marker check only; a full pixel decode happens in the CV worker."""
    return (len(blob) >= 4 and len(blob) <= MAX_IMAGE_BYTES
            and blob.startswith(b"\xff\xd8") and blob.endswith(b"\xff\xd9"))


def decode_legacy_image(payload: bytes) -> bytes | None:
    """Accept complete JPEG, JSON {image: Base64}, or plain Base64 JPEG."""
    if is_jpeg(payload):
        return payload
    if payload.startswith(b"\xff\xd8"):
        return None  # Incomplete JPEG; never reinterpret as chunks.

    stripped = payload.strip()
    if stripped.startswith(b"{"):
        try:
            obj = json.loads(stripped.decode("utf-8"))
            encoded = obj.get("image") if isinstance(obj, dict) else None
        except (UnicodeDecodeError, ValueError):
            return None
        if not isinstance(encoded, str):
            return None
    else:
        # Raw chunk headers contain binary control bytes. Only accept ASCII
        # and a plausible Base64 prefix for the legacy text format.
        try:
            encoded = stripped.decode("ascii")
        except UnicodeDecodeError:
            return None

    if encoded.startswith("data:"):
        prefix, sep, encoded = encoded.partition(",")
        if not sep or "base64" not in prefix.lower():
            return None
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None
    return decoded if is_jpeg(decoded) else None


@dataclass
class PendingFrame:
    total_chunks: int
    total_len: int
    last_seen: float
    chunks: dict[int, bytes] = field(default_factory=dict)


class FrameAssembler:
    """Reconstruct complete JPEGs from unordered chunk messages."""

    def __init__(self) -> None:
        self.pending: dict[int, PendingFrame] = {}
        self.recently_completed: dict[int, float] = {}
        self.completed_frames = 0
        self.invalid_messages = 0
        self.expired_frames = 0
        self.received_chunks = 0
        self.duplicate_chunks = 0
        self.dropped_frames = 0

    def cleanup(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for frame_id, frame in list(self.pending.items()):
            if now - frame.last_seen > FRAME_TIMEOUT_SECONDS:
                self.pending.pop(frame_id, None)
                self.expired_frames += 1
                LOG.warning("Incomplete frame %s expired (%s/%s chunks)",
                            frame_id, len(frame.chunks), frame.total_chunks)
        for frame_id, timestamp in list(self.recently_completed.items()):
            if now - timestamp > RECENT_FRAME_SECONDS:
                self.recently_completed.pop(frame_id, None)

    def feed(self, payload: bytes, now: float | None = None) -> tuple[int, bytes] | None:
        now = time.monotonic() if now is None else now
        self.cleanup(now)
        if len(payload) <= HEADER.size or len(payload) > HEADER.size + CHUNK_SIZE:
            self.invalid_messages += 1
            return None

        frame_id, chunk_idx, total_chunks, total_len = HEADER.unpack_from(payload)
        chunk = payload[HEADER.size:]
        if (not 0 < total_len <= MAX_IMAGE_BYTES
                or not 0 < total_chunks <= 65535
                or total_chunks != (total_len + CHUNK_SIZE - 1) // CHUNK_SIZE
                or chunk_idx >= total_chunks):
            self.invalid_messages += 1
            return None
        expected_len = min(CHUNK_SIZE, total_len - chunk_idx * CHUNK_SIZE)
        if len(chunk) != expected_len:
            self.invalid_messages += 1
            return None
        if frame_id in self.recently_completed:
            return None

        frame = self.pending.get(frame_id)
        if frame is None:
            if len(self.pending) >= MAX_INFLIGHT_FRAMES:
                oldest = min(self.pending, key=lambda key: self.pending[key].last_seen)
                LOG.warning("Too many incomplete frames; dropping frame %s", oldest)
                self.pending.pop(oldest)
                self.dropped_frames += 1
            frame = PendingFrame(total_chunks, total_len, now)
            self.pending[frame_id] = frame
        elif frame.total_len != total_len or frame.total_chunks != total_chunks:
            self.pending.pop(frame_id, None)
            self.invalid_messages += 1
            LOG.warning("Inconsistent header for frame %s", frame_id)
            return None

        frame.last_seen = now
        if chunk_idx in frame.chunks:
            self.duplicate_chunks += 1
            if frame.chunks[chunk_idx] != chunk:
                self.pending.pop(frame_id, None)
                self.invalid_messages += 1
                LOG.warning("Conflicting duplicate chunk: frame=%s index=%s", frame_id, chunk_idx)
            return None
        frame.chunks[chunk_idx] = chunk
        self.received_chunks += 1
        if len(frame.chunks) < total_chunks:
            if chunk_idx == total_chunks - 1 or len(frame.chunks) % 25 == 0:
                LOG.info("Chunk progress frame=%s %s/%s (%.1f%%)",
                         frame_id, len(frame.chunks), total_chunks,
                         100.0 * len(frame.chunks) / total_chunks)
            return None

        jpeg = b"".join(frame.chunks[i] for i in range(total_chunks))
        self.pending.pop(frame_id, None)
        if len(jpeg) != total_len or not is_jpeg(jpeg):
            self.invalid_messages += 1
            LOG.warning("Invalid reconstructed JPEG for frame %s", frame_id)
            return None
        self.recently_completed[frame_id] = now
        self.completed_frames += 1
        LOG.info("Complete frame %s: %s bytes, %s chunks", frame_id, len(jpeg), total_chunks)
        return frame_id, jpeg


class SubscriberService:
    def __init__(self) -> None:
        self.assembler = FrameAssembler()
        self.redis = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
            socket_connect_timeout=5, socket_timeout=5,
        )
        self.image_count = 0
        self.redis_ok = 0
        self.redis_failed = 0
        self.message_count = 0
        self.legacy_frames = 0
        self.saved_count = 0
        self.save_failed = 0
        self.connected = False

    def handle_image(self, jpeg: bytes, frame_id: int | None) -> None:
        # Keep the expected CV-worker Redis format: raw JPEG bytes only.
        try:
            queue_length = self.redis.lpush(REDIS_QUEUE_NAME, jpeg)
        except redis.RedisError as exc:
            self.redis_failed += 1
            LOG.error("Redis LPUSH failed (frame=%s): %s", frame_id, exc)
        else:
            self.redis_ok += 1
            LOG.info("JPEG -> Redis %s; frame=%s bytes=%s queue_length=%s",
                     REDIS_QUEUE_NAME, frame_id if frame_id is not None else "legacy",
                     len(jpeg), queue_length)

        if SAVE_RECEIVED_IMAGES:
            try:
                SAVE_DIR.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                ident = "legacy" if frame_id is None else f"frame_{frame_id:010d}"
                path = SAVE_DIR / f"{stamp}_{ident}.jpg"
                with path.open("xb") as output:
                    output.write(jpeg)
                self.saved_count += 1
                LOG.info("JPEG saved: %s", path)
            except OSError as exc:
                self.save_failed += 1
                LOG.warning("Could not save JPEG: %s", exc)
        self.image_count += 1

    def log_statistics(self) -> None:
        assembler = self.assembler
        LOG.info(
            "[STATS] mqtt_messages=%d | completed_chunk_frames=%d | legacy_frames=%d "
            "| chunk_parts=%d | duplicate_chunks=%d | invalid_chunks=%d "
            "| timeout_frames=%d | dropped_frames=%d | inflight_frames=%d "
            "| redis_ok=%d | redis_failed=%d | saved=%d | save_failed=%d",
            self.message_count, assembler.completed_frames, self.legacy_frames,
            assembler.received_chunks, assembler.duplicate_chunks,
            assembler.invalid_messages, assembler.expired_frames,
            assembler.dropped_frames, len(assembler.pending), self.redis_ok,
            self.redis_failed, self.saved_count, self.save_failed,
        )

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.connected = True
            LOG.info("[MQTT] Connected to %s:%s client_id=%s",
                     MQTT_BROKER, MQTT_PORT, MQTT_CLIENT_ID)
            result, mid = client.subscribe(MQTT_TOPIC, qos=0)
            LOG.info("[MQTT] Subscribe requested topic=%s qos=0 result=%s mid=%s",
                     MQTT_TOPIC, result, mid)
            if result != 0:
                LOG.error("[MQTT] Subscribe request failed: %s", result)
        else:
            self.connected = False
            LOG.error("[MQTT] Connect failed: %s", reason_code)

    def on_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        # The callback runs for both paho-mqtt 1.x and 2.x.
        LOG.info("[MQTT] Subscription acknowledged mid=%s granted_qos=%s",
                 mid, granted_qos)
        if any(getattr(qos, "is_failure", False) or
               (isinstance(qos, int) and qos >= 128) for qos in granted_qos):
            LOG.error("[MQTT] Subscription rejected for topic=%s", MQTT_TOPIC)

    def on_disconnect(self, client, userdata, *args):
        self.connected = False
        LOG.warning("[MQTT] Disconnected: %s", args)

    def on_message(self, client, userdata, msg):
        self.message_count += 1
        payload = msg.payload
        LOG.info("[MQTT] Message #%d topic=%s bytes=%d qos=%s retain=%s",
                 self.message_count, msg.topic, len(payload), msg.qos, msg.retain)
        try:
            # Legacy formats are complete JPEG, JSON-Base64, and plain Base64.
            # If none matches, parse binary chunks using a strict 12-byte header.
            legacy = decode_legacy_image(payload)
            if legacy is not None:
                self.legacy_frames += 1
                LOG.info("[IMAGE] Complete JPEG received via legacy/direct payload (%d B)",
                         len(legacy))
                self.handle_image(legacy, frame_id=None)
            else:
                before_invalid = self.assembler.invalid_messages
                result = self.assembler.feed(payload)
                if result is not None:
                    frame_id, jpeg = result
                    LOG.info("[IMAGE] Chunk frame assembled id=%s total=%d B",
                             frame_id, len(jpeg))
                    self.handle_image(jpeg, frame_id=frame_id)
                elif self.assembler.invalid_messages != before_invalid:
                    LOG.warning("[MQTT] Message #%d rejected: invalid chunk/payload",
                                self.message_count)
        except Exception:
            LOG.exception("[MQTT] Message #%d processing failed", self.message_count)
        finally:
            if self.message_count % LOG_EVERY == 0:
                self.log_statistics()


def create_client(service: SubscriberService):
    # The installed paho version decides which callback API is in use.
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    except AttributeError:
        client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.on_connect = service.on_connect
    client.on_subscribe = service.on_subscribe
    client.on_disconnect = service.on_disconnect
    client.on_message = service.on_message
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    return client


def main() -> None:
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                        format="%(asctime)s %(levelname)-7s %(message)s")
    service = SubscriberService()
    LOG.info("[START] MQTT broker=%s:%s topic=%s client_id=%s",
             MQTT_BROKER, MQTT_PORT, MQTT_TOPIC, MQTT_CLIENT_ID)
    LOG.info("[START] Redis=%s:%s/%s queue=%s",
             REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_QUEUE_NAME)
    LOG.info("[START] JPEG formats=chunked / binary / JSON Base64 / Base64; "
             "save_images=%s save_dir=%s log_every=%s",
             SAVE_RECEIVED_IMAGES, SAVE_DIR.resolve(), LOG_EVERY)
    client = create_client(service)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        LOG.info("Stopped by user")
    except Exception:
        LOG.exception("[FATAL] Subscriber stopped unexpectedly")
        raise
    finally:
        service.log_statistics()
        client.disconnect()


if __name__ == "__main__":
    main()
