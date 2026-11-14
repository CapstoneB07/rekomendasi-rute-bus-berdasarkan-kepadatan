# Sweep headcount YOLO, RT-DETR, dan RF-DETR

Jalankan dari root monorepo `rekomendasi-rute-bus-berdasarkan-kepadatan`,
menggunakan environment CV yang memiliki dependensi `cv/requirements.txt`.

```powershell
# Dependency tambahan untuk RF-DETR (pasang pada environment CV).
python -m pip install -r cv/script/requirements-rfdetr.txt

# RF-DETR dari checkpoint lokal Anda; hasil masuk outputs/sweeps/rfdetr_uji_01/.
python cv/script/headcount_sweep_test.py --model cv/script/models/weights_rt-detr.pt --model-type rfdetr --model-class-id 1 --name rfdetr_uji_01

# RT-DETR fine-tuned; hasil masuk outputs/sweeps/rtdetr_uji_01/.
python cv/script/headcount_sweep_test.py --model cv/script/models/rtdetr-l.pt --model-type rtdetr --name rtdetr_uji_01

# YOLO; nama folder bisa berbeda untuk setiap eksperimen.
python cv/script/headcount_sweep_test.py --model cv/script/models/weights.pt --name yolo_uji_01

# Path lengkap folder hasil, seperti opsi --output sebelumnya.
python cv/script/headcount_sweep_test.py --model cv/script/models/rtdetr-l.pt --output D:/hasil-capstone/rtdetr_01

# Folder induk + nama eksperimen.
python cv/script/headcount_sweep_test.py --model cv/script/models/rtdetr-l.pt --output D:/hasil-capstone --name rtdetr_02
```

`--model-type auto` adalah default dan memilih predictor dari arsitektur checkpoint,
termasuk checkpoint dengan nama umum seperti `best.pt`. Opsi eksplisit `yolo`,
`rtdetr`, dan `rfdetr` tersedia. Dataset tetap menggunakan format anotasi YOLO;
RT-DETR maupun RF-DETR tidak memerlukan konversi label.

Contoh di atas membutuhkan checkpoint RT-DETR Ultralytics, misalnya `rtdetr-l.pt`
atau hasil fine-tuning RT-DETR dengan Ultralytics. Unduhan bobot pretrained dapat
dilakukan oleh Ultralytics jika model tersebut belum tersedia secara lokal.
File lokal `models/weights_rt-detr.pt` berisi state_dict RF-DETR Nano dengan backbone
DINO, bukan checkpoint RT-DETR Ultralytics. Gunakan `--model-type rfdetr` atau
`auto`; tidak perlu mengganti nama atau mengonversi checkpoint.
Adapter berada di `rfdetr_adapter.py`; dependency RF-DETR tidak diperlukan saat
hanya menjalankan YOLO atau RT-DETR Ultralytics.

`--rfdetr-variant auto` mengenali varian standar dari bentuk tensor checkpoint.
Jika arsitektur training dimodifikasi, pilih `--rfdetr-variant nano|small|medium|large|base`
sesuai training dan gunakan checkpoint yang menyimpan `model_config` lengkap.
Varian tanpa metadata yang tidak dapat dipastikan akan menghasilkan pesan error.
Checkpoint RF-DETR tanpa nama kelas menggunakan `class_0`, dst. dan memerlukan
`--model-class-id` agar slot kelas tidak ditebak. Checkpoint lama bisa memakai
ID 1 meskipun hanya dilatih pada satu kelas; angka ini tidak harus sama dengan
`--gt-class-id` pada dataset YOLO. Contoh untuk checkpoint lokal di atas memilih
ID model 1, sedangkan kelas orang pada anotasi YOLO adalah 0.

RF-DETR menerima gambar RGB. Adapter mengonversi hasil OpenCV BGR ke RGB dan
menyaring kelas sebelum memakai filter area/aspect ratio yang sama dengan YOLO.
Ukuran gambar bawaan disesuaikan ke kelipatan `patch_size * num_windows` bila perlu,
dan ukuran aktual dicatat di CSV. Gunakan `--imgsz 320 640` untuk memilih daftar
ukuran sendiri; ukuran eksplisit yang tidak kompatibel menghasilkan error.

`--name` menerima satu nama folder. Untuk path bersarang/absolut gunakan `--output`.
Tanpa keduanya, folder default lama tetap `outputs/sweeps/current_rt/`.
Path output bawaan dihitung dari lokasi skrip melalui `cv_paths.py`;
path relatif pada `--output` mengikuti folder terminal.
Jika folder hasil sudah ada, file CSV dengan nama sama ditulis ulang seperti perilaku sebelumnya;
gunakan nama berbeda untuk mempertahankan setiap eksperimen.

Hasil tetap berupa `all_experiments.csv`, `configuration_summary.csv`,
`top_configurations.csv`, dan anotasi `top_annotated/rank_*/`.
Kolom `model_type` pada CSV detail mencatat arsitektur yang digunakan.

RT-DETR dan RF-DETR tidak memakai NMS, sehingga IoU tidak divariasikan dan kolom `iou` pada CSV
dikosongkan. Default menjalankan 12 konfigurasi. `--full-sweep` menjalankan 84
konfigurasi RT-DETR / RF-DETR (7 confidence x 4 ukuran gambar x 3 preprocessing),
atau 336 konfigurasi YOLO yang menyertakan variasi IoU.
Pilih parameter pada validation set; gunakan test set hanya untuk evaluasi final.

Pengujian offline tanpa memuat checkpoint:

```powershell
python -m unittest discover -s cv/script -p test_headcount_sweep_test.py -v
```
