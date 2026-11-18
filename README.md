# Antigravity Task Overlay (Windows)

Aplikasi floating overlay desktop **Always-on-Top** ultra-ringan dan hemat resource untuk memantau semua task, sesi, kuota model, dan progres real-time dari Antigravity Agent secara langsung di layar Windows.

---

## Fitur yang Diimplementasikan

### 1. Konsep Tata Letak Pill Dinamis (4 Baris) & Resizable Window

- **Baris 1 (Header Sesi)**: Status dot, judul sesi dinamis (otomatis mengikuti lebar jendela tanpa terpotong kaku), dan Animated Model Badge.
- **Baris 2 (Proses Real-time)**: Ikon vektor + teks proses aktif, indikator perubahan baris (`+baris` hijau / `-baris` merah) untuk pembuatan/pengeditan file, atau tampilan sekilas command (`Cmd: ...`) saat diklik.
- **Baris 3 (Response Command Sekilas, dinamis)**: Muncul dengan animasi slide ketika proses *running command* diklik dan memiliki output/response (`Output: ...`), lalu menutup otomatis setelah beberapa detik.
- **Baris 4 (Indikator Proses Latar Belakang, dinamis)**: Berada di posisi baris ke-3 saat normal, dan otomatis bergeser ke baris ke-4 apabila Baris 3 sedang menampilkan *response command*.
- **Ukuran Panjang & Tinggi Jendela Fleksibel**: Tarik tepi kiri atau kanan jendela untuk mengubah panjang (lebar) jendela secara leluasa (`360px` – `1200px`), atau tarik tepi bawah saat mode *expanded* untuk mengubah tinggi panel log. Seluruh elemen UI menyesuaikan diri secara dinamis dan ukuran disimpan ke `config.json`.

---

### 2. Fase Status Baris 2 (Real-time Task Line)

**Fase Thinking Dinamis**
- Ditampilkan baik saat giliran baru dimulai maupun di sela antar eksekusi tool ketika tool sebelumnya telah selesai (`DONE`) dan model sedang berpikir untuk langkah berikutnya.
- Ikon: `brain` (ungu `#c084fc`). Teks: `Thinking...`
- Tidak tertahan pada nama task lama ketika agen sudah beralih kembali ke fase *thinking*.

**Fase Working & Indikator Diff Baris (`+baris -baris`)**
- Ditampilkan selama tool sedang dieksekusi.
- Saat membuat file (`write_file`), mengedit baris, atau menghapus baris (`edit_file`), begitu perubahan selesai diterapkan (`applied`), aplikasi menampilkan statistik `+baris` (hijau `#34d399`) dan `-baris` (merah `#f87171`) tepat di samping nama proses pada Baris 2 maupun pada daftar riwayat log.
- Saat menjalankan proses *command* (`Ran ...`), pengguna dapat mengklik baris proses tersebut untuk menampilkan sekilas perintah asli yang dijalankan di Baris 2 (`Cmd: ...`) diikuti tampilan sekilas *response* / output perintah tersebut di Baris 3 (`Output: ...`).

**Fase Membutuhkan Input User (Decision Required)**
- Ditampilkan saat agen memanggil `ask_question` atau menerbitkan artifact dengan `RequestFeedback: true`.
- Ikon: `help_circle` (amber `#f59e0b`). Status dot berubah warna menjadi amber.
- Teks: `Membutuhkan input user: <Judul Keputusan>`
- Efek animasi shimmer glow berwarna amber menyapu teks secara dinamis untuk menarik perhatian.
- Tooltip menampilkan rincian pertanyaan dan daftar pilihan opsi.
- Status kembali otomatis begitu pengguna mengirim jawaban atau prompt baru.

**Fase Selesai — Urutan Transisi Ringkasan (Completion Summary Sequence)**
- Saat task selesai (`IDLE`), overlay menjalankan 3 tahap transisi berurutan secara otomatis:
  1. **Tahap 1** (~2.6 detik): Ikon `circle_check` hijau (`#10b981`) + teks `Tugas selesai`.
  2. **Tahap 2** (~6.5 detik): Bertransisi halus (fade & slide) ke ikon `sparkles` biru neon (`#38bdf8`) + teks `Ringkasan: <intisari perbaikan/implementasi>`. Jika teks panjang, marquee auto-scroll menggulirkan seluruh ringkasan.
  3. **Tahap 3**: Bertransisi kembali secara mulus ke ikon `circle_check` hijau + teks `Tugas selesai`.
- **Replay Interaktif**: Klik pada teks atau ikon baris task kapan saja saat idle untuk memutar ulang tampilan ringkasan.
- **Ekstraksi Ringkasan Otomatis**: Ringkasan diambil dari kalimat pertama respon model (`PLANNER_RESPONSE`), dibersihkan dari seluruh formatting markdown. Fallback: daftar file yang diedit, lalu event tool terakhir.
- **Pembatalan Cepat**: Jika prompt baru masuk atau keputusan user dibutuhkan saat sekuens berjalan, timer langsung dibatalkan dan status beralih seketika.

**Fase Standby**
- Ditampilkan saat tidak ada sesi aktif sama sekali.
- Ikon: `terminal`. Teks: `Standby / Menunggu task...`

---

### 3. Baris 3 — Background Process Indicator

- Muncul otomatis tepat di bawah baris 2 ketika terdeteksi proses latar belakang aktif (`PowerShell`, `Python`, `Node`, `Git`, `CMD`, dsb.).
- Animasi slide-down / slide-up: tinggi baris (`0px` ke `17px`), tinggi pill (`38px` ke `58px`), dan tinggi jendela keseluruhan bertransisi mulus menggunakan kurva *OutCubic*.
- Ikon terminal berwarna sesuai tipe proses (biru neon `#38bdf8` untuk PowerShell, ungu `#c084fc` untuk lainnya).
- Menampilkan nama proses, ringkasan perintah, atau task ID sebagai teks deskripsi.
- Tombol dismiss mini (silang) di ujung kanan untuk menutup/mengabaikan info secara instan.
- Tooltip menampilkan detail lengkap: nama proses, perintah, dan task ID.

---

### 4. Hover Floating Action Card (3 Tombol)

- Tombol **Pin**, **Expand/Collapse Log**, dan **Close** disembunyikan secara default agar pill tampak bersih.
- Muncul dalam card gelap melayang dengan animasi fade-in (160ms, kurva *OutCubic*) saat kursor memasuki area pill.
- Menghilang dengan animasi fade-out (180ms, kurva *InCubic*) saat kursor keluar, dengan debounce 140ms untuk menghindari flicker.
- Card melayang di atas elemen lain (menutup sementara duration badge dan kuota ring) tanpa menggeser layout.

---

### 5. Dropdown Log Hierarki

- **Level 1 — Session Bar**: Pemilih sesi membentang penuh, lengkap dengan indikator status dot (hijau/putih) dan badge jumlah task.
- **Level 2 — Accordion Header**: Header ringkasan aksi (`Explored files, ran commands, edited files`) persis seperti tampilan asli Antigravity.
- **Level 3 — Log Timeline**: Log diindentasi ke dalam dengan tag jenis file berwarna (`PY` biru, `MD` ungu, `JS` kuning, `</>` oranye untuk HTML, `{}` biru untuk CSS, dsb.), ikon kategori, dan chevron `>` di sisi kanan setiap baris.
- **Zero Layout Void**: Tinggi pill dikunci presisi (`38px` / `58px`) sehingga dropdown menempel tepat di bawah pill tanpa celah kosong.
- Smooth expand & collapse: animasi tinggi jendela dengan kurva *Cubic Easing* saat membuka atau menutup log.

---

### 6. Circular Quota Ring

- Gauge melingkar dinamis yang menampilkan sisa kuota context window model dalam persentase dan jumlah token.
- Warna adaptif: hijau (>50%), kuning (20–50%), merah (<20%).
- Tooltip saat hover menampilkan rincian token terpakai vs batas context window model.
- Klik untuk beralih tampilan antara `%` dan `token count`.

---

### 7. Animated Model Badge

- Badge nama model (misal: `Gemini Flash`, `Claude Sonnet`) muncul dengan animasi expand & fade-in selama ~4.5 detik di sebelah judul sesi ketika proses baru dimulai.
- Menghilang secara halus setelah durasi selesai agar ruang tampilan kembali bersih.
- Klik pada judul sesi (baris 1) untuk memunculkan kembali badge model kapan saja.

---

### 8. Micro-animations Umum

- **Shimmer Glow Swipe**: Efek kilau linear gradient menyapu teks baris 2 secara kontinu saat proses `RUNNING` (biru-putih) atau menunggu keputusan (amber-putih-kuning).
- **Smooth Task Transition**: Saat teks baris 2 berganti, teks lama meluncur ke atas dan memudar, digantikan teks baru yang masuk dari bawah secara halus (220ms).
- **Marquee Auto-Scroll**: Jika teks baris 2 melebihi lebar pill, teks bergulir otomatis ke kiri dan kembali secara mulus. Timer animasi berhenti otomatis saat tidak ada overflow dan agen idle.

---

### 9. Active Run Timer

- Timer durasi hanya berjalan saat proses sedang aktif (`RUNNING`), bukan menghitung keseluruhan umur sesi.
- Mengukur waktu dari awal giliran (*turn*) saat ini: `12s`, `1m 24s`, `1h 5m 3s`.
- Saat proses selesai, timer berhenti dan menampilkan durasi eksekusi giliran terakhir.
- Timer disembunyikan sepenuhnya saat tidak ada sesi aktif.

---

### 10. Adaptive Polling & Efisiensi Resource

- Frekuensi polling adaptif: 350ms saat proses aktif atau menunggu keputusan, 1.2 detik saat idle.
- Timer animasi berhenti otomatis saat agen idle dan teks tidak overflow — zero CPU waste.
- Database SQLite dibaca dalam mode `read-only` (WAL mode) — zero disk write.

---

### 11. Integrasi Ekstensi Antigravity IDE & VS Code (Auto-Start, Auto-Close & Panel Konfigurasi)

- **Activity Bar Icon & Sidebar Panel**: Menambahkan ikon aplikasi khusus di Activity Bar IDE (Antigravity IDE maupun IDE berbasis VS Code). Saat diklik, menampilkan panel **Kontrol & Konfigurasi** interaktif secara langsung di dalam IDE.
- **Siklus Hidup Otomatis (Auto-Start & Auto-Close)**:
  - **Auto-Start**: Saat IDE dibuka (`onStartupFinished`), ekstensi secara otomatis menjalankan aplikasi Task Overlay di latar belakang tanpa jendela terminal.
  - **Auto-Close**: Saat IDE ditutup, ekstensi menghentikan aplikasi secara otomatis (dilengkapi mekanisme *parent process watchdog* `--parent-pid` di `main.py` sehingga overlay tetap tertutup otomatis meskipun proses IDE dihentikan paksa).
- **Live Hot-Reload Configuration**: Semua perubahan pengaturan di panel IDE langsung tersimpan ke `config.json` dan diterapkan secara *real-time* (~320ms) oleh jendela Task Overlay yang sedang aktif tanpa perlu me-restart aplikasi:
  - **Kontrol Proses**: Status proses live (`Aktif (PID ...)` / `Berhenti`) beserta tombol **Jalankan**, **Hentikan**, dan **Restart**.
  - **Otomatisasi & Jendela**: Toggle *Auto-Start saat IDE Dibuka*, *Auto-Close saat IDE Ditutup*, *Always on Top (Pin)*, serta slider *Opacity / Transparansi Jendela (40% – 100%)*.
  - **Ukuran & Posisi Layar**: Slider *Panjang / Lebar Jendela (360px – 1200px)*, *Tinggi Log Saat Expanded (250px – 820px)*, input koordinat `X` / `Y`, serta 5 tombol *Quick Snap Position* (*Kiri Atas*, *Tengah Atas*, *Kanan Atas*, *Kiri Bawah*, *Kanan Bawah*).
  - **Komponen UI & Indikator**: Toggle on/off untuk *Lingkaran Kuota Token*, *Timer Durasi Eksekusi*, *Badge Model AI*, *Statistik Baris (+baris -baris)*, *Indikator Background Process*, dan *Ringkasan Penyelesaian Otomatis*.
  - **Durasi Animasi & Performa**: Slider untuk *Kecepatan Auto-Scroll Teks*, *Durasi Tampil Badge Model*, *Durasi Tampil Ringkasan Selesai*, *Durasi Sekilas Command & Response*, dan *Interval Polling Realtime*.
- **Status Bar Shortcut**: Indikator `Task Overlay: Aktif` / `Task Overlay: Nonaktif` di Status Bar kanan bawah IDE untuk membuka panel konfigurasi dengan satu klik.

---

### 12. Vector Icon Pack

Icon SVG vektor tajam (*Lucide / Feather style*), tanpa emoji, mencakup:
`terminal`, `file_text`, `edit`, `file_plus`, `search`, `tool`, `user`, `clock`, `pin`, `pin_off`, `chevron_down`, `chevron_up`, `chevron_right`, `close`, `cpu`, `brain`, `circle_check`, `sparkles`, `help_circle`, `alert_circle`, `corner_down_right`, `dot`.

---

## Efisiensi & Resource Usage

| Parameter | Nilai | Keterangan |
| :--- | :--- | :--- |
| **RAM (Memory)** | ~42–50 MB | Native PyQt6 bindings dengan DirectComposition DWM. |
| **CPU Usage** | 0.0% – 0.1% | Timer animasi berhenti otomatis saat idle dan tidak ada overflow. |
| **Disk I/O** | 0 Write, Read-Only | SQLite dibaca dengan `mode=ro` URI pada WAL mode. |
| **Polling Interval** | 320ms (aktif) / 1.1s (idle) | Frekuensi adaptif, otomatis cepat saat RUNNING atau menunggu input. |

---

## Cara Menggunakan & Distribusi

### Opsi 1: Instalasi dari File `.vsix` (Untuk Pengguna Umum)

1. Pastikan **Python 3 (>= 3.9)** sudah terpasang di sistem.
2. Pasang file `antigravity-task-overlay-1.0.0.vsix` di Antigravity IDE / VS Code melalui menu **Extensions -> `...` -> Install from VSIX...** (atau jalankan CLI `antigravity-ide --install-extension antigravity-task-overlay-1.0.0.vsix`).
3. Saat ekstensi pertama kali dijalankan, ekstensi akan otomatis memeriksa `PyQt6`. Jika belum tersedia di Python sistem, ekstensi akan membuat virtual environment di `~/.antigravity-task-overlay/venv` dan memasang `PyQt6` secara otomatis.
4. Konfigurasi pengguna (`config.json`), PID, dan log error (`err.log`) disimpan secara persisten di `~/.antigravity-task-overlay/` sehingga tidak hilang saat ekstensi diperbarui.

### Opsi 2: Build `.vsix` & Install Lokal (Untuk Developer)

- Hanya membangun file `.vsix` untuk release:
  ```bash
  python install_extension.py --pack-only
  ```
- Membangun `.vsix` sekaligus memasangnya ke folder ekstensi lokal (`~/.antigravity-ide/extensions`, `~/.antigravity/extensions`, `~/.vscode/extensions`):
  ```bash
  python install_extension.py
  ```
  Lalu muat ulang jendela IDE (`Ctrl+Shift+P` -> `Developer: Reload Window`).

### Opsi 3: Menjalankan Mandiri (Standalone)

- Mode tanpa jendela terminal: Klik 2x `run_silent.vbs`.
- Mode console/debugging: Jalankan `python main.py` atau klik 2x `run.bat`.
- Menghentikan aplikasi mandiri: Klik tombol `X` pada jendela overlay, jalankan `python main.py --stop`, atau klik 2x `stop.bat`.

---

## Struktur File

```
d:\Task Overlay\
├── package.json            # Manifest ekstensi Antigravity IDE / VS Code
├── extension.js            # Core ekstensi IDE (Auto-setup venv, Lifecycle & Webview Panel)
├── install_extension.py    # Packager VSIX self-contained & installer lokal
├── requirements.txt        # Dependensi Python (PyQt6)
├── media/
│   └── activity-icon.svg   # Ikon vektor Activity Bar IDE
├── paths.py                # Resolusi direktori data persisten (~/.antigravity-task-overlay)
├── main.py                 # Entry point aplikasi Python (PID lock, --stop & Parent Watchdog)
├── overlay_window.py       # UI Window PyQt6 (4-Row Dynamic Pill + Live Config Hot-Reload)
├── animated_task_label.py  # Task Label dengan Shimmer, Diff (+baris -baris) & Marquee Scroll
├── model_badge.py          # Badge Model Animasi (Fade-in saat start/switch model)
├── quota_widget.py         # Circular Quota & Token Progress Ring
├── icons.py                # Vector SVG Icon Pack
├── monitor.py              # State Engine (Transcript parser, Diff & Command Response extractor)
├── styles.py               # Dark Glassmorphism QSS styling
├── run_silent.vbs          # Silent background launcher (opsional standalone)
├── run.bat                 # Normal launcher (opsional standalone)
├── stop.bat                # Quick stop script
└── README.md               # Dokumentasi ini
```
