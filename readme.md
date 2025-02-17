# Simple Spot Trading Bot  
  
Simple Spot Trading Bot adalah bot trading yang dirancang untuk melakukan perdagangan di pasar spot menggunakan Binance API. Bot ini memanfaatkan strategi berbasis analisis teknikal dan manajemen risiko untuk melakukan trading cryptocurrency secara otomatis.
  
---  
  
## Fitur  
  
- **Trading Otomatis**: Melakukan pembelian dan penjualan secara otomatis berdasarkan strategi yang telah ditentukan
- **Analisis Teknikal**: Menggunakan indikator RSI untuk analisis market
- **Manajemen Risiko**: Mengatur stop loss dan take profit untuk mengendalikan risiko perdagangan
- **Monitoring Real-time**: Pemantauan pasar dan status trading secara real-time
- **Database Integration**: Pencatatan dan tracking semua transaksi dalam database
- **Notifikasi Telegram**: Mengirim notifikasi melalui Telegram untuk setiap aktivitas trading
- **Position Sizing**: Perhitungan ukuran posisi trading yang optimal
- **Multi-Pair Trading**: Mendukung trading multiple cryptocurrency pairs
- **Performance Tracking**: Pelacakan dan analisis performa trading

---

## Struktur Proyek

```
simple-spot-trading-bot/  
│  
├── src/                           # Direktori source code  
│   ├── trade_manager.py          # Mengelola logika trading utama
│   ├── database_manager.py       # Menangani operasi database
│   ├── status_monitor.py         # Memantau status bot
│   ├── market_operations.py      # Menangani operasi pasar
│   ├── trade_operations.py       # Menangani operasi trading
│   ├── send_telegram_message.py  # Mengirim notifikasi Telegram
│   ├── calculate_position_size.py # Menghitung ukuran posisi
│   ├── _calculate_rsi.py         # Menghitung indikator RSI
│   ├── handle_stop_loss.py       # Menangani stop loss
│   ├── get_balances.py          # Mengambil informasi saldo
│   ├── performance_tracking.py   # Melacak performa trading
│   ├── risk_management.py       # Mengelola risiko trading
│   └── utils/                   # Utilitas pendukung
│  
├── config/  
│   └── settings.py              # Konfigurasi dan parameter bot
│  
└── main.py                      # Entry point dan implementasi TradingBot class
```

---

## Komponen Utama

### 1. TradingBot Class (main.py)
- Kelas utama yang mengatur seluruh operasi trading
- Menginisialisasi koneksi ke Binance API
- Mengatur manajemen database dan monitoring
- Mengelola sesi trading dan error handling

### 2. Trade Manager (trade_manager.py)
- Implementasi logika trading utama
- Pengambilan keputusan beli/jual
- Eksekusi order dan manajemen posisi

### 3. Database Manager (database_manager.py)
- Pengelolaan database transaksi
- Pencatatan historical data
- Tracking performa trading

### 4. Market Operations (market_operations.py)
- Interaksi dengan Binance API
- Pengambilan data market
- Eksekusi order market

### 5. Risk Management (risk_management.py)
- Implementasi stop loss dan take profit
- Perhitungan position sizing
- Manajemen risiko portfolio

### 6. Performance Tracking (performance_tracking.py)
- Analisis performa trading
- Perhitungan metrics
- Reporting dan monitoring

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
2. Edit `config/settings.py` dan atur:
   - API Key dan Secret Key Binance
   - Token dan Group ID Telegram
   - Parameter trading (RSI, multiplier, dll)
   - Konfigurasi trading pairs

---

## Penggunaan

Untuk menjalankan bot:

```bash
python main.py
```

Bot akan:
1. Menginisialisasi koneksi ke Binance
2. Memulai monitoring market
3. Melakukan trading berdasarkan strategi yang dikonfigurasi
4. Mengirim notifikasi via Telegram untuk setiap aktivitas

---

## Kontribusi

Kami menyambut kontribusi! Silakan buat pull request atau buka issue untuk diskusi lebih lanjut.

---

## Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE).

---

## Kontak

Jika Anda memiliki pertanyaan atau saran, silakan hubungi saya melalui email: [addhe.warman@gmail.com](mailto:addhe.warman@gmail.com).