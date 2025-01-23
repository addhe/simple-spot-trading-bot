Pada kode di strategy.py, kita dapat melihat implementasi kelas PriceActionStrategy, yang memfokuskan pada pembuatan strategi berdasarkan analisis harga historis dan volatilitas pasar (menggunakan ATR). Berikut adalah beberapa poin penting yang perlu diperhatikan:

1. Inisialisasi Kelas dan Binance Client
Kelas PriceActionStrategy memerlukan simbol trading (misalnya BTCUSDT) dan opsi use_testnet yang memungkinkan untuk menggunakan Binance Testnet.
Binance Client: Diinisialisasi dengan menggunakan API Key dan Secret, dan bisa disesuaikan untuk Testnet atau Live environment.
2. Caching Data Historis
Bot menyimpan data historis dalam cache untuk meningkatkan performa, dengan file cache yang disimpan menggunakan pickle. Data hanya valid untuk 5 menit, yang berguna untuk menghindari pengambilan data yang berulang-ulang dari Binance API.
Fungsi load_cached_data untuk memuat data yang disimpan, sementara save_to_cache untuk menyimpan data yang diambil.
3. Pengambilan Data Historis
get_historical_data menggunakan API Binance untuk mengambil data candlestick dengan interval 1m (1 menit) untuk periode 1 hari (24 jam).
Data yang diambil mencakup harga buka, tinggi, rendah, tutup, volume, dll., dan data ini diubah menjadi DataFrame pandas untuk pemrosesan lebih lanjut.
Fitur retry (dengan library retrying) diterapkan agar jika terjadi kesalahan dalam pengambilan data, percobaan diulang hingga 5 kali dengan jeda 2 detik.
4. Perhitungan Harga Beli dan Jual Dinamis
Harga Beli Dinamis: Berdasarkan perhitungan rata-rata bergerak dari harga penutupan (closing price) dalam 10 periode terakhir dan volatilitas pasar yang dihitung menggunakan Average True Range (ATR).
Harga Jual Dinamis: Mirip dengan harga beli dinamis, namun dikalkulasi dengan menambahkan margin (5%) dan faktor volatilitas.
Fungsi calculate_dynamic_buy_price dan calculate_dynamic_sell_price mengembalikan harga yang dihitung berdasarkan analisis harga pasar saat itu.
5. Perhitungan ATR (Average True Range)
ATR dihitung dengan mengambil perbedaan harga tertinggi dan terendah, serta harga penutupan sebelumnya. ATR menggambarkan volatilitas pasar dan digunakan untuk menyesuaikan harga beli dan jual sesuai dengan fluktuasi pasar.
6. Pengelolaan Kesalahan
Di seluruh kelas, banyak pengelolaan kesalahan yang diterapkan menggunakan blok try-except. Jika ada kesalahan dalam proses pengambilan data atau perhitungan, bot akan mencatat kesalahan tersebut dan melanjutkan eksekusi.