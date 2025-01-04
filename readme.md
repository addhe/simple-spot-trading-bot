# Simple Spot Trading Bot

Simple Spot Trading Bot adalah bot trading yang dirancang untuk melakukan perdagangan di pasar spot menggunakan Binance API. Bot ini memanfaatkan strategi berbasis analisis harga untuk menentukan waktu yang optimal untuk membeli dan menjual aset.

---

## Fitur

- **Trading Otomatis**: Melakukan pembelian dan penjualan secara otomatis berdasarkan strategi yang telah ditentukan.
- **Pengaturan Dinamis**: Menghitung harga beli dan jual secara dinamis berdasarkan data historis.
- **Notifikasi Telegram**: Mengirim notifikasi melalui Telegram saat transaksi dilakukan.
- **Log Rotasi**: Mengelola file log dengan rotasi otomatis untuk menjaga ukuran file log tetap terkendali.

---

## Struktur Proyek

```
simple-spot-trading-bot/
│
├── src/
│   ├── bot.py                 # Kode utama untuk bot trading
│   ├── check_price.py         # Fungsi untuk memeriksa harga dan strategi trading
│   ├── strategy.py            # Implementasi strategi trading
│   └── notifikasi_telegram.py # Modul untuk mengirim notifikasi melalui Telegram
│
├── config/
│   ├── config.py              # Konfigurasi untuk bot
│   └── settings.py            # Pengaturan API dan parameter lainnya
│
├── historical_data.pkl        # Data historis untuk analisis
├── latest_activity.pkl        # Menyimpan aktivitas terbaru bot
├── bot.log                    # File log untuk mencatat aktivitas bot
└── main.py                    # Entry point untuk menjalankan bot
```

---

## Instalasi

### 1. Clone Repositori

```bash
git clone https://github.com/addhe/simple-spot-trading-bot.git
cd simple-spot-trading-bot
```

### 2. Instal Dependensi

Pastikan Python 3.x telah terinstal, kemudian jalankan perintah berikut:

```bash
pip install -r requirements.txt
```

### 3. Konfigurasi

- Edit file `config/settings.py` untuk menambahkan API Key dan Secret Key dari Binance.
- Sesuaikan parameter lainnya sesuai kebutuhan Anda.

---

## Penggunaan

Untuk menjalankan bot, gunakan perintah berikut:

```bash
python main.py
```

Bot akan berjalan dan melakukan trading berdasarkan strategi yang telah ditentukan.

---

## Log Rotasi

Bot ini menggunakan mekanisme rotasi log otomatis untuk menjaga ukuran file log tetap terkendali. Pastikan Anda telah mengatur konfigurasi log sesuai kebutuhan.

---

## Kontribusi

Kami menyambut kontribusi Anda! Jika Anda ingin berkontribusi, silakan buat pull request atau buka issue untuk diskusi lebih lanjut.

---

## Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE).

---

## Kontak

Jika Anda memiliki pertanyaan atau saran, silakan hubungi saya melalui email: [addhe.warman@gmail.com](mailto:addhe.warman@gmail.com).