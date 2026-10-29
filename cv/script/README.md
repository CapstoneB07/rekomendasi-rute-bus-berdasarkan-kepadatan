# Computer vision dan eksperimen perangkat

Folder ini berisi deteksi headcount, persiapan dataset, training YOLO, serta
pengukuran MQTT dan daya INA226. Semua path bawaan mengacu pada lokasi `script/`
melalui `cv_paths.py`, sehingga tidak bergantung pada folder terminal saat menjalankan skrip.

```text
script/
  headcount.py                       # Deteksi gambar statis + benchmark
  headcount_video.py                 # Deteksi video + kirim hasil ke backend
  headcount_sweep_test.py            # Evaluasi hitungan dari anotasi YOLO
  dataset_deduplicator.py            # Salin gambar unik + laporan kualitas
  mqtt_latency_subscriber.py         # Latency MQTT gambar
  mqtt_ina226_latency_subscriber.py  # Pengukuran daya INA226
  cv_paths.py                        # Lokasi dataset, model, media, dan output
  datasets/
    dataset_full/                    # Dataset bus, anotasi YOLO: train/valid/test
    dataset_test/                    # 103 gambar evaluasi lama
    head.v1i.yolo26/                  # Dataset kepala/orang untuk notebook training
    ground_truth.csv                 # Hitungan manual untuk dataset_test
  models/                            # Semua checkpoint .pt
  media/                             # Gambar dan video contoh
  notebooks/
    yolo_training.ipynb
  outputs/
    headcount/                       # Gambar hasil dan CSV headcount
    sweeps/
      legacy_headcount/              # Hasil lama, format CSV berbeda
      current/                       # Dibuat saat sweep baru dijalankan
    telemetry/                       # CSV MQTT/INA226 dan received_images_latency/
    training/
      legacy_runs/                   # Metadata training lama
```

## Menjalankan

Contoh berikut dijalankan dari root proyek:

```powershell
python script/headcount.py
python script/headcount_video.py
python script/headcount_sweep_test.py --help
python script/headcount_sweep_test.py --split val --model script/models/weights.pt
python script/dataset_deduplicator.py --input script/datasets/raw_dataset --output script/datasets/dataset_cleaned
python script/mqtt_latency_subscriber.py
python script/mqtt_ina226_latency_subscriber.py
```

Dari folder `script/`, gunakan misalnya `python headcount.py`.
Path yang diberikan secara eksplisit melalui argumen CLI tetap mengikuti folder terminal.
Direktori output yang diperlukan dibuat otomatis.

Dependensi deteksi/evaluasi: `ultralytics`, `torch`, `opencv-python`, `numpy`,
`PyYAML`; video memakai `requests`, subscriber memakai `paho-mqtt`.
Notebook juga memakai `matplotlib`, `IPython`, dan kernel Jupyter.
Gunakan OpenCV dengan dukungan GUI untuk window hasil; paket headless tidak menyediakan window.

Ubah konfigurasi di bagian atas setiap skrip sesuai eksperimen.
`headcount.py` memakai `models/weights.pt`; `headcount_video.py` dan sweep
memakai `models/yolo26n.pt` secara bawaan. Tombol X, tombol keyboard, atau Ctrl+C
menutup tampilan gambar statis.

Notebook berada di `notebooks/yolo_training.ipynb` dan dapat dijalankan dengan kernel
berlokasi di root proyek, `script/`, atau `script/notebooks/`. Dataset bawaan tetap
`head.v1i.yolo26`; ganti `DATASET_PATH` ke `dataset_full` untuk training dataset bus.
Hasil training baru disimpan di `outputs/training/headcount_yolo26/`.
Cell persiapan memperbarui `data.yaml` dengan path absolut lokal sebelum training.
Output cell yang tersimpan adalah riwayat eksekusi lama dan dapat memuat nama/path lama;
jalankan ulang cell untuk memperbaruinya.

## Data dan hasil eksperimen

- `ground_truth.csv` berpasangan dengan 103 gambar di `dataset_test/`. Sweep saat ini
  membaca anotasi bounding box YOLO, sehingga folder gambar lama beserta CSV hitungan
  manualnya tidak dapat langsung dipakai sebagai `--data`.
- Gunakan validation set untuk memilih parameter. Simpan test set untuk evaluasi final.
- CSV dan metadata eksperimen lama dipertahankan apa adanya, termasuk path historisnya.
  `outputs/sweeps/legacy_headcount/` berasal dari versi evaluasi lama; jangan gabungkan
  CSV-nya langsung dengan hasil versi saat ini.
- Kelima model memiliki hash SHA-256 berbeda. Tiga dataset tidak memiliki gambar
  identik antar-dataset berdasarkan SHA-256; ini tidak menyingkirkan kemiripan visual.
- Dataset lokal besar dan output training/sweep baru diabaikan Git melalui `.gitignore`.
  Simpan salinan dataset dan checkpoint penting di penyimpanan cadangan.

## Kandidat yang boleh dipertimbangkan untuk dihapus

Belum ada file yang dihapus dalam perapian ini. Ukuran berikut perkiraan MiB.

| Lokasi | Ukuran | Pertimbangan |
| --- | ---: | --- |
| `outputs/training/legacy_runs/` | 0,002 | Hanya berisi `args.yaml`, tanpa checkpoint atau metrik. Bisa dihapus jika metadata percobaan lama tidak diperlukan. |
| `outputs/sweeps/legacy_headcount/top_annotated/` | 17,8 | Visualisasi yang dapat dibuat ulang jika skrip, data, model, dan konfigurasi versi eksperimen tersebut tersedia. Simpan CSV ringkasan untuk laporan. |
| `models/weights_rt-detr.pt` | 115,2 | Tidak dirujuk oleh skrip/notebook saat ini. Hapus hanya jika eksperimen pembandingan RT-DETR sudah ditinggalkan dan ada salinan model. |
| `models/best.pt`, `models/yolo26s.pt` | 5,1 + 19,5 | Tidak dirujuk oleh konfigurasi bawaan saat ini; bisa tetap dipakai melalui `--model`. Pastikan asal dan kegunaan checkpoint sebelum menghapus. |
| `media/image.png` | 0,4 | Tidak dirujuk oleh skrip/notebook saat ini. Bisa dihapus bila memang hanya gambar percobaan tanpa kebutuhan dokumentasi. |

Pertahankan `models/weights.pt`, `models/yolo26n.pt`, ketiga dataset, ground truth,
dan CSV pengujian yang digunakan sebagai bukti eksperimen capstone.
