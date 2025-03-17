# Simple Spot Trading Bot  
  
Simple Spot Trading Bot adalah bot trading yang dirancang untuk melakukan perdagangan di pasar spot menggunakan Binance API. Bot ini memanfaatkan strategi berbasis analisis teknikal dan manajemen risiko untuk menentukan waktu yang optimal untuk membeli dan menjual aset.  
  
---  
  
## Fitur  
  
- **Trading Otomatis**: Melakukan pembelian dan penjualan secara otomatis berdasarkan strategi yang telah ditentukan.  
- **Web Interface**: Antarmuka web untuk monitoring dan kontrol manual trading.
- **Pengaturan Dinamis**: Menghitung harga beli dan jual secara dinamis berdasarkan data historis.  
- **Notifikasi Telegram**: Mengirim notifikasi melalui Telegram saat transaksi dilakukan.  
- **Log Rotasi**: Mengelola file log dengan rotasi otomatis untuk menjaga ukuran file log tetap terkendali.  
- **Manajemen Risiko**: Mengatur stop loss dan take profit untuk mengendalikan risiko perdagangan.  
- **Multi-Pasangan Mata Uang**: Mendukung beberapa pasangan mata uang seperti BTC/USDT, ETH/USDT, dan SOL/USDT.  
- **Database SQLite**: Menyimpan data historis dan transaksi untuk analisis dan tracking.

---

## Komponen Utama

### main.py
File utama yang menjalankan bot trading, termasuk:
- Inisialisasi koneksi ke Binance API
- Manajemen database dan data historis
- Implementasi logika trading utama
- Monitoring status dan performa trading

### web.py
Web interface untuk bot trading, menyediakan:
- Endpoint untuk pembelian dan penjualan manual
- Monitoring balance dan aset
- Kontrol dan manajemen trading

### src/
Direktori berisi modul-modul pendukung:
- **trade_manager.py**: Mengatur eksekusi order beli/jual
- **db_manager.py**: Manajemen database SQLite
- **historical_data.py**: Pengumpulan dan analisis data historis
- **send_telegram_message.py**: Notifikasi via Telegram
- Dan modul pendukung lainnya

---

## Struktur Proyek

```
simple-spot-trading-bot/  
│  
├── src/                      # Modul-modul pendukung  
│   ├── __init__.py
│   ├── trade_manager.py      # Manajemen trading
│   ├── db_manager.py         # Manajemen database
│   ├── historical_data.py    # Pengumpulan data historis
│   ├── send_telegram_message.py  # Notifikasi Telegram
│   └── ... (modul lainnya)
│  
├── config/  
│   └── settings.py           # Konfigurasi dan parameter  
│  
├── logs/                     # Direktori log files
├── main.py                   # Bot trading utama
├── web.py                    # Web interface
├── requirements.txt          # Dependensi Python
└── README.md                # Dokumentasi
```

---

## Instalasi

### 1. Clone Repositori

```bash
git clone https://github.com/addhe/simple-spot-trading-bot.git
cd simple-spot-trading-bot
```

### 2. Instal Dependensi

Pastikan Python 3.x telah terinstal, kemudian jalankan:

```bash
pip install -r requirements.txt
```

### 3. Konfigurasi

1. Copy `config/settings.example.py` ke `config/settings.py`
2. Edit `config/settings.py`:
   - Tambahkan Binance API Key dan Secret
   - Konfigurasi Telegram Token dan Group ID
   - Sesuaikan parameter trading

---

## Penggunaan

### Menjalankan Bot Trading

```bash
python main.py
```

### Menjalankan Web Interface

```bash
python web.py
```
Web interface akan tersedia di `http://localhost:8080`

---

## Monitoring dan Logging

Bot menggunakan sistem logging yang komprehensif:
- Log trading: `logs/bot/bot.log`
- Log web interface: `trading_bot.log`
- Database SQLite: `trading_data.db`

---

## Kontribusi

Kami menyambut kontribusi! Silakan buat pull request atau buka issue untuk diskusi lebih lanjut.

---

## Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE).

---

## Kontak

Jika Anda memiliki pertanyaan atau saran, silakan hubungi saya melalui email: [addhe.warman@gmail.com](mailto:addhe.warman@gmail.com).

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