1. Konfigurasi dan Koneksi ke Binance
API Binance: Bot ini menggunakan binance.client.Client untuk mengakses API Binance menggunakan API Key dan Secret yang disediakan di file settings.py.
Database: Bot menggunakan SQLite (bot_trading.db) untuk menyimpan status terkini dari aktivitas trading yang dilakukan (misalnya: apakah sudah membeli, harga beli, harga jual, dll).
2. Data Storage
DataStorage digunakan untuk mengelola penyimpanan status terakhir setiap simbol (pair crypto).
Fungsi save_latest_activity dan load_latest_activity memungkinkan bot untuk menyimpan dan mengambil status dari setiap pasangan trading seperti status beli/jual, harga, dan informasi stop loss/take profit.
3. Strategi dan Pemilihan Aksi (Buy/Sell)
PriceActionStrategy digunakan untuk menentukan aksi yang harus diambil berdasarkan data pasar.
Bot secara berkala akan mengecek harga pasar dan memutuskan apakah harus membeli atau menjual berdasarkan kondisi yang ditentukan dalam strategi.
4. Logika Trading
check_prices: Fungsi ini akan memeriksa harga untuk setiap pasangan crypto dan melakukan eksekusi pembelian atau penjualan sesuai dengan kondisi dan strategi yang ada.
Pembelian: Jika aksi adalah BUY dan bot belum membeli simbol tersebut sebelumnya, bot akan menghitung jumlah yang akan dibeli dan mengeksekusi order BUY.
Penjualan: Jika aksi adalah SELL dan bot sudah membeli simbol tersebut, bot akan mengeksekusi order SELL. Ini juga termasuk pemantauan kondisi tertentu yang ditentukan oleh strategi (misalnya, harga sudah mencapai target).
Penjualan berdasarkan strategi: Bahkan jika aksi bukan SELL secara eksplisit, strategi akan mengecek apakah ada kondisi yang memerlukan penjualan berdasarkan harga terbaru (misalnya, harga turun di bawah stop loss).
5. Pengelolaan Order
Bot memeriksa apakah ada order yang aktif dengan menggunakan has_active_orders sebelum mencoba untuk membeli atau menjual. Ini mencegah pengiriman order ganda untuk simbol yang sama.
6. Perhitungan Kuantitas
Fungsi calculate_dynamic_quantity menghitung jumlah yang dapat dibeli berdasarkan saldo USDT yang tersedia. Fungsi ini memperhitungkan batasan kuantitas, harga, dan nilai minimum notional yang ditetapkan oleh Binance.
7. Pemrosesan Pesan
Bot mengirimkan notifikasi Telegram melalui notifikasi_buy dan notifikasi_sell setelah membeli atau menjual.
8. Loop Utama Bot (run)
Bot menjalankan sebuah loop yang terus berjalan untuk mengecek harga setiap 60 detik dan memproses keputusan untuk membeli atau menjual.
Pertanyaan atau area yang mungkin perlu ditinjau lebih lanjut:
Penanganan Kesalahan: Apakah ada kasus kegagalan API yang mungkin tidak tertangani dengan baik? Mungkin ada potensi untuk menambahkan retry atau pengelolaan kesalahan lebih lanjut.

Pengelolaan Penggunaan Sumber Daya: Karena bot ini berjalan terus-menerus, apakah ada batasan atau pengelolaan sumber daya untuk memastikan bot tidak menghabiskan sumber daya tanpa perlu?

Notifikasi: Apakah ada pesan atau pengingat penting yang mungkin terlupakan dalam proses eksekusi? Misalnya, pengecekan saldo atau status koneksi internet.