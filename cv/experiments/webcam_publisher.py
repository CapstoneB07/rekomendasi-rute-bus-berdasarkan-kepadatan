"""Pengganti ESP32-CAM untuk uji coba: kirim frame webcam laptop ke MQTT.

Memakai broker, topik, dan format payload (JPEG mentah) yang sama dengan
firmware, jadi seluruh rantai ikut teruji:

    webcam -> HiveMQ -> worker/mqtt_subscriber.py -> Redis -> worker/cv_worker.py
           -> Supabase (kepadatan_live, kamera_live) -> /operator

Jalankan dari folder cv/ (venv aktif), setelah Redis, mqtt_subscriber.py dan
cv_worker.py hidup:

    python experiments/webcam_publisher.py            # kamera 0, 5 frame/detik
    python experiments/webcam_publisher.py --camera 1 --fps 2 --preview

Tekan q di jendela preview atau Ctrl+C untuk berhenti.
"""

import argparse
import time

import cv2
import paho.mqtt.client as mqtt

# Samakan dengan worker/mqtt_subscriber.py.
BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "capstone/stefany/esp32s3/camera/base64"


def buat_klien() -> mqtt.Client:
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)  # paho >= 2
    except AttributeError:
        return mqtt.Client()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--camera", type=int, default=0, help="indeks webcam (default 0)")
    ap.add_argument("--fps", type=float, default=5.0, help="frame per detik (default 5)")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--quality", type=int, default=75, help="kualitas JPEG 1-100")
    ap.add_argument("--topic", default=TOPIC)
    ap.add_argument("--broker", default=BROKER)
    ap.add_argument("--preview", action="store_true", help="tampilkan jendela preview")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit(f"Webcam indeks {args.camera} tidak bisa dibuka.")

    klien = buat_klien()
    klien.connect(args.broker, PORT, keepalive=30)
    klien.loop_start()

    interval = 1.0 / args.fps
    terkirim = 0
    print(f"Mengirim ke {args.broker}:{PORT} topik {args.topic} @ {args.fps} fps. Ctrl+C untuk berhenti.")
    try:
        while True:
            mulai = time.monotonic()
            ok, frame = cap.read()
            if not ok:
                print("Gagal membaca frame webcam, coba lagi...")
                time.sleep(0.5)
                continue

            h, w = frame.shape[:2]
            if w > args.width:
                frame = cv2.resize(frame, (args.width, int(h * args.width / w)))

            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
            if ok:
                klien.publish(args.topic, jpg.tobytes(), qos=0)
                terkirim += 1
                print(f"frame #{terkirim} terkirim ({len(jpg) / 1024:.1f} KB)")

            if args.preview:
                cv2.imshow("webcam_publisher (q = keluar)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            time.sleep(max(0.0, interval - (time.monotonic() - mulai)))
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        klien.loop_stop()
        klien.disconnect()


if __name__ == "__main__":
    main()
