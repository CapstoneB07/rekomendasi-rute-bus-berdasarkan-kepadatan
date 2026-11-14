# Uji latensi ESP32-S3 camera

Subscriber ini sesuai dengan publisher `KodeWifi_KirimGambardanTimestamp (1).ino`:

- Broker: `broker.hivemq.com:1883`.
- Topic: `capstone/stefany/esp32s3/camera/base64`, QoS 0.
- Payload JSON: `{"timestamp": 1793270000000, "image": "<Base64 JPEG>"}`.
- `timestamp` adalah Unix epoch milidetik setelah `esp_camera_fb_get()`, sebelum
  Base64 encoding, penyusunan JSON, reconnect MQTT bila diperlukan, dan publish.
- Publisher ini tidak mengirim data tegangan, arus, atau daya.

## Menjalankan

Dari root monorepo `rekomendasi-rute-bus-berdasarkan-kepadatan`:

```powershell
python -m pip install paho-mqtt
python cv/script/mqtt_latency_subscriber.py
```

Jika Python terminal belum memiliki dependency, gunakan interpreter environment
CV yang sudah berisi `paho-mqtt`. `--help` dan pengujian offline tidak memerlukan paket itu.

Mulai subscriber hingga muncul `Subscribe berhasil`, lalu jalankan publisher.
Tekan Ctrl+C untuk berhenti. CSV sudah di-flush setiap pesan dan ditutup saat keluar,
termasuk jika dihentikan saat sinkronisasi NTP atau koneksi broker.

Opsi:

```powershell
# Catat latensi tanpa menyimpan JPEG.
python cv/script/mqtt_latency_subscriber.py --no-save-images

# Tentukan file CSV baru sendiri; tidak menimpa file yang sudah ada.
python cv/script/mqtt_latency_subscriber.py --csv cv/script/outputs/telemetry/uji_kamera_01.csv

# Bila UDP NTP tidak tersedia: catat RAW saja, tanpa mengklaim koreksi berhasil.
python cv/script/mqtt_latency_subscriber.py --skip-ntp
```

## Output

Path bawaan mengikuti lokasi skrip melalui `cv_paths.py`, independen dari folder terminal:

```text
cv/script/outputs/telemetry/
  mqtt_camera_latency_<tanggal>_<jam>_<id_sesi>.csv
  received_images_latency/<id_sesi>/<timestamp_esp32>_<sequence>.jpg
```

CSV baru dibuat per sesi sehingga schema dan data log sebelumnya tetap utuh.
Header ditulis sebelum koneksi; sesi tanpa pesan tetap menghasilkan CSV berisi header.
`sequence` adalah urutan penerimaan lokal, bukan frame ID ESP32; publisher belum
mengirim frame ID sehingga subscriber tidak bisa menghitung packet loss dari nomor ini.

Kolom utama:

| Kolom | Arti |
| --- | --- |
| `device_timestamp_ms`, `device_timestamp_utc` | Waktu dari ESP32 |
| `receive_pc_raw_ms`, `receive_pc_raw_utc` | Waktu awal callback PC, sebelum parsing/decode/save |
| `ntp_synced`, `ntp_offset_ms`, `ntp_rtt_ms`, `ntp_sample_utc` | Hasil kalibrasi NTP awal sesi; sample dengan RTT terendah dipilih |
| `receive_pc_corrected_ms`, `receive_pc_corrected_utc` | Clock PC + offset NTP; kosong jika NTP gagal |
| `latency_raw_ms` | Clock PC raw dikurangi timestamp ESP32 |
| `latency_corrected_ms` | Clock PC terkoreksi dikurangi timestamp ESP32; kosong jika NTP gagal |
| `measurement_valid`, `status`, `error` | Kelayakan pengukuran dan penjelasan masalah |
| `mqtt_payload_bytes`, `base64_chars`, `jpeg_bytes` | Ukuran JSON, Base64, dan JPEG |
| `json_parse_ms`, `base64_decode_ms`, `image_save_ms` | Durasi pekerjaan subscriber; tidak ditambahkan ke latensi penerimaan |
| `mqtt_topic`, `mqtt_qos`, `mqtt_retain`, `mqtt_dup` | Metadata pesan MQTT |
| `save_image`, `file_path` | Keberhasilan dan lokasi penyimpanan JPEG |

Pesan rusak tetap dicatat dengan status `invalid_payload`, `invalid_timestamp`, atau
`invalid_image`. Pemeriksaan JPEG hanya memeriksa marker awal/akhir, bukan decoding pixel.
Pesan `retained`, timestamp mendahului PC (`clock_ahead`), dan NTP gagal
(`ntp_unavailable`) tidak masuk statistik latensi terkoreksi. Nilai negatif tetap
disimpan untuk diagnosis. `image_save_error` dapat tetap memiliki `measurement_valid=1`
karena waktu penerimaan berhasil diukur sebelum penulisan JPEG gagal.

## Membaca hasil

Latensi ini mencakup encoding di ESP32, penundaan reconnect/antrean, jaringan,
broker, dan waktu sampai callback PC. Durasi capture kamera tidak terukur.
Pengolahan pesan sebelumnya dapat ikut menunda callback pesan berikutnya.
Ini bukan pengukuran waktu jaringan saja.

Pastikan serial ESP32 menunjukkan sinkronisasi NTP berhasil. Offset WIB pada
`configTime()` mengatur representasi waktu lokal; Unix epoch tidak perlu ditambah 7 jam.
Kalibrasi PC diambil pada awal sesi dan tidak membuktikan clock ESP32 bebas error.
RTT NTP dicatat sebagai informasi kualitas, bukan jaminan batas error pengukuran.
Untuk sesi panjang atau setelah perubahan clock PC, mulai ulang sesi agar kalibrasi diperbarui.

## Pengujian offline

```powershell
python -m unittest discover -s cv/script -p test_mqtt_latency_subscriber.py -v
```

Pengujian memakai pesan simulasi dan direktori sementara. Tidak ada koneksi broker,
pengiriman MQTT, atau data simulasi yang ditulis ke log eksperimen sesungguhnya.
