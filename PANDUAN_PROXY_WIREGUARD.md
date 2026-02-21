# Panduan: Routing WireGuard ke Residential Proxy via VPS

Pernahkah Anda bertanya "bagaimana cara menggabungkan koneksi **VPN WireGuard di HP** dengan **Residential Proxy di VPS**?" Panduan ini menjawabnya secara tuntas.

Sistem akan bekerja seperti ini:
```text
(HP) WireGuard Client ---> (VPS) WireGuard Server ---> (VPS) tun2socks ---> Residential Proxy ---> Jaringan Internet
```
Dengan begitu, **seluruh trafik** dari HP Anda secara murni akan keluar seolah-olah berasal dari IP rumahan milik Residential Proxy tersebut (misal AS/Eropa). Ini adalah standar proteksi bypass tertinggi, sering digunakan untuk botting dan verifikasi identitas (seperti SheerID).

---

## 1️⃣ Siapkan WireGuard Server di VPS

Gunakan installer otomatis tercepat untuk Linux (Ubuntu/Debian):

```bash
# Unduh script installer
curl -O https://raw.githubusercontent.com/angristan/wireguard-install/master/wireguard-install.sh
chmod +x wireguard-install.sh

# Jalankan installer (Enter terus pakai setting bawaan)
sudo ./wireguard-install.sh
```

- Ketika ditanya **Client name**, isi dengan: `hp-saya`
- Script tersebut otomatis menghasilkan file bernama **`hp-saya.conf`**. 
- Untuk memindahkannya ke HP Anda dengan cepat, tampilkan sebagai **QR Code** di terminal VPS:
  ```bash
  sudo apt install qrencode -y
  qrencode -t ansiutf8 < hp-saya.conf
  ```
- **Buka aplikasi WireGuard di HP -> Scan QR code di layar PC Anda.** Koneksi dasar sudah siap!

---

## 2️⃣ Install `tun2socks` di VPS

`tun2socks` adalah alat mungil buatan ekosistem Go (golang) yang sangat sakti: alat ini mengubah protokol Proxy (SOCKS5/HTTP) menjadi format virtual *Network Interface* (TUN) yang bisa dirouting oleh sistem operasi.

Jalankan perintah ini di VPS:

```bash
# Unduh binary terbaru untuk arsitektur Linux x64
wget https://github.com/xjasonlyu/tun2socks/releases/latest/download/tun2socks-linux-amd64.zip
unzip tun2socks-linux-amd64.zip

# Pindahkan ke bin sistem agar bisa dieksekusi dari manapun
sudo mv tun2socks-linux-amd64 /usr/local/bin/tun2socks
sudo chmod +x /usr/local/bin/tun2socks
```

---

## 3️⃣ Mulai "Membelokkan" Trafik (Routing)

Sekarang, VPS Anda murni merouting trafik klien (Subnet WireGuard: `10.66.66.0/24`) menuju Residential Proxy (lewat `tun2socks`). 

Buat file script operasi via `nano start-proxy.sh` dan isi kodenya:

```bash
#!/bin/bash

# --- GANTI BAGIAN INI ---
# Contoh SOCKS5: "socks5://USER:PASS@HOST:PORT"
# Contoh HTTP:   "http://USER:PASS@HOST:PORT"
PROXY_URL="socks5://rahasia:pass123@192.168.1.100:1080" 
# ------------------------

echo "[+] Membuat virtual TUN interface (tun1)..."
ip tuntap add mode tun dev tun1
ip addr add 198.18.0.1/15 dev tun1
ip link set dev tun1 up

echo "[+] Menjalankan tun2socks ke Residential Proxy..."
# Opsi '&' meletakkan proses di background (tidak memblokir terminal)
tun2socks -device tun://tun1 -proxy $PROXY_URL &

sleep 2

echo "[+] Mendaftarkan routing rule (memaksa trafik WireGuard ke tun1)..."
# Wireguard klien biasanya diberi subnet 10.66.66.0/24 oleh angristan-script
ip rule add from 10.66.66.0/24 table 100
ip route add default dev tun1 table 100

echo ""
echo "🔥 BERHASIL! Seluruh trafik WireGuard Anda kini dirouting melalui Residential Proxy."
```

Simpan file, beri hak eksekusi, lalu jalankan:
```bash
chmod +x start-proxy.sh
sudo ./start-proxy.sh
```

---

## 4️⃣ Testing di HP Anda

1. Pastikan Anda **terkoneksi** ke server WireGuard VPS via aplikasi HP.
2. Buka browser di HP dan navigasi ke: [https://ipinfo.io](https://ipinfo.io)
3. Cek blok bagian `IP` dan kategori `ASN/ISP`.
4. Jika **sukses**, maka informasi jaringan yang muncul akan sesuai dengan IP **Residential Proxy** milik Anda (bukan IP Cloud/Datacenter tempat VPS Anda berada). Kualitas anonimitas perangkat kini berada pada titik puncak (menyerupai *real device*).

---

## 🛑 Cara Mematikan Proxy Routing (Kembali Normal)

Sewaktu-waktu Anda tidak lagi memakai Residential Proxy dan menginginkan kecepatan asli VPS, rute tersebut bisa dihapus. 

Buat file `nano stop-proxy.sh`:
```bash
#!/bin/bash
echo "[-] Mematikan tun2socks..."
pkill -f tun2socks

echo "[-] Menghapus routing wireguard..."
ip rule del from 10.66.66.0/24 table 100 2>/dev/null
ip link delete tun1 2>/dev/null

echo "✅ Sistem Routing Virtual dinonaktifkan."
```
Lalu jalankan saja `sudo bash stop-proxy.sh`.

### 💡 Keuntungan Metode Ini:
- **Zero Configuration on Phone:** Anda tak perlu aplikasi injeksi Proxy macam Shadowrocket di HP. Cukup satu toggle tombol VPN bawaan OS (WireGuard kernel mode). Ini hemat baterai drastis.
- **Tahan Bocor (No Leak):** Sistem bekerja di Kernel Route Linux (`iptables/iproute2`). Memaksa semua aplikasi HP (Tiktok, IG, dll) lewat Residential IP (menyerupai perangkat murni US/Europe).
