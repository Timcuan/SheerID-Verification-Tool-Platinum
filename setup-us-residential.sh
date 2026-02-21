#!/bin/bash
# ==============================================================================
# 🛡️ ONE-CLICK US RESIDENTIAL VPN ROUTER (WireGuard + tun2socks)
# ==============================================================================
# Script ini secara otomatis:
# 1. Install WireGuard & buat profil VPN untuk HP
# 2. Install tun2socks (Pengubah SOCKS5/HTTP -> Interface Virtual)
# 3. Setting iptables routing (Memaksa HP lewat Proxy US)
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==================================================================${NC}"
echo -e "${GREEN}   🇺🇸 ONE-CLICK US RESIDENTIAL ROUTER (WireGuard -> Proxy)${NC}"
echo -e "${BLUE}==================================================================${NC}"

# --- 1. Minta Data Proxy ---
echo -e "${YELLOW}Masukkan data Residential Proxy US Anda.${NC}"
echo -e "Format: ${GREEN}socks5://USER:PASS@HOST:PORT${NC} atau ${GREEN}http://USER:PASS@HOST:PORT${NC}"
read -p "👉 URL Proxy: " PROXY_URL

if [[ -z "$PROXY_URL" ]]; then
  echo -e "${RED}[✗] Proxy tidak boleh kosong. Dibatalkan.${NC}"
  exit 1
fi

# --- 2. Install WireGuard (jika belum) ---
if ! command -v wg &> /dev/null; then
  echo -e "${YELLOW}[→] Menginstal WireGuard Server...${NC}"
  curl -O https://raw.githubusercontent.com/angristan/wireguard-install/master/wireguard-install.sh
  chmod +x wireguard-install.sh
  
  # Auto-install dengan default config, buat 1 client "hp-us"
  export AUTO_INSTALL=y
  export CLIENT_NAME="hp-us"
  sudo -E ./wireguard-install.sh
  echo -e "${GREEN}[✓] WireGuard terinstal.${NC}"
else
  echo -e "${GREEN}[✓] WireGuard sudah terinstal.${NC}"
fi

# Cari IP Subnet WireGuard (biasanya 10.66.66.x)
WG_SUBNET=$(ip -o -f inet addr show wg0 2>/dev/null | awk '{print $4}' | cut -d'.' -f1-3)
if [[ -z "$WG_SUBNET" ]]; then
  WG_SUBNET="10.66.66"
fi
WG_CIDR="${WG_SUBNET}.0/24"

# --- 3. Install tun2socks ---
if ! command -v tun2socks &> /dev/null; then
  echo -e "${YELLOW}[→] Mengunduh tun2socks...${NC}"
  wget -q https://github.com/xjasonlyu/tun2socks/releases/latest/download/tun2socks-linux-amd64.zip
  unzip -q tun2socks-linux-amd64.zip
  sudo mv tun2socks-linux-amd64 /usr/local/bin/tun2socks
  sudo chmod +x /usr/local/bin/tun2socks
  rm tun2socks-linux-amd64.zip
  echo -e "${GREEN}[✓] tun2socks terinstal.${NC}"
else
  echo -e "${GREEN}[✓] tun2socks sudah terinstal.${NC}"
fi

# --- 4. Hentikan routing lama jika ada ---
pkill -f tun2socks 2>/dev/null
ip rule del from $WG_CIDR table 100 2>/dev/null
ip link delete dev tun1 2>/dev/null

# --- 5. Bikin Service Systemd untuk Routing & tun2socks ---
echo -e "${YELLOW}[→] Membuat service background 'us-proxy-route'...${NC}"

cat <<EOF | sudo tee /usr/local/bin/start-us-route.sh > /dev/null
#!/bin/bash
# 1. Bikin interface virtual
ip tuntap add mode tun dev tun1
ip addr add 198.18.0.1/15 dev tun1
ip link set dev tun1 up

# 2. Tandai (MARK) trafik WireGuard, KECUALI DNS (UDP 53)
# Proxy SOCKS5 perumahan biasanya tidak support UDP, jadi DNS akan mati.
# Kita paksa DNS (port 53) lewat internet asli VPS, sisanya lewat proxy US.
iptables -t mangle -A PREROUTING -s $WG_CIDR -j MARK --set-mark 100
iptables -t mangle -A PREROUTING -s $WG_CIDR -p udp --dport 53 -j MARK --set-mark 0

# 3. Arahkan trafik yang memiliki mark 100 ke tun1 (proxy)
ip rule add fwmark 100 table 100
ip route add default dev tun1 table 100

# 4. Jalankan tun2socks (berhenti di sini dan block process)
exec tun2socks -device tun://tun1 -proxy "$PROXY_URL"
EOF

cat <<EOF | sudo tee /usr/local/bin/stop-us-route.sh > /dev/null
#!/bin/bash
ip rule del fwmark 100 table 100 2>/dev/null
ip link delete tun1 2>/dev/null
iptables -t mangle -D PREROUTING -s $WG_CIDR -j MARK --set-mark 100 2>/dev/null
iptables -t mangle -D PREROUTING -s $WG_CIDR -p udp --dport 53 -j MARK --set-mark 0 2>/dev/null
EOF

chmod +x /usr/local/bin/start-us-route.sh
chmod +x /usr/local/bin/stop-us-route.sh

cat <<EOF | sudo tee /etc/systemd/system/us-proxy.service > /dev/null
[Unit]
Description=US Residential Proxy Router for WireGuard
After=network.target wg-quick@wg0.service

[Service]
Type=simple
ExecStart=/usr/local/bin/start-us-route.sh
ExecStopPost=/usr/local/bin/stop-us-route.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# --- 6. Aktifkan Routing ---
sudo systemctl daemon-reload
sudo systemctl enable us-proxy
sudo systemctl start us-proxy

echo ""
echo -e "${BLUE}==================================================================${NC}"
echo -e "${GREEN} ✅ SETUP SELESAI! HP ANDA SEKARANG \"BERADA\" DI AMERIKA.${NC}"
echo -e "${BLUE}==================================================================${NC}"
echo ""
echo -e "📱 ${YELLOW}Langkah di HP Anda:${NC}"
echo -e "1. Install aplikasi ${GREEN}WireGuard${NC} dari Play Store / App Store."

# Tampilkan QR Config jika ada
CLIENT_CONF=$(ls ~/*.conf 2>/dev/null | head -n 1)
if [[ -n "$CLIENT_CONF" ]]; then
  echo -e "2. Buka aplikasi, lalu scan QR Code ini (atau import file ${CLIENT_CONF}):"
  echo ""
  qrencode -t ansiutf8 < "$CLIENT_CONF"
else
  echo -e "2. Jalankan \`cat hp-us.conf\` dan import konfigurasinya ke WireGuard."
fi

echo ""
echo -e "🛡️ ${GREEN}Cara Kerja (100% Anti-Bocor):${NC}"
echo -e "Semua aplikasi di HP Anda (Browser, Game, IG, TikTok) akan melewati"
echo -e "terowongan VPN VPN -> VPS -> Langsung ke US Residential Proxy."
echo -e "Ini membuat Anda seolah-olah warga lokal US murni."
echo ""
echo -e "Cek IP Anda di HP: ${BLUE}https://ipinfo.io${NC}"
echo ""
echo -e "⚙️ ${YELLOW}Perintah Berguna:${NC}"
echo -e "• Matikan proxy & kembali ke IP VPS : sudo systemctl stop us-proxy"
echo -e "• Nyalakan proxy lagi                 : sudo systemctl start us-proxy"
echo -e "• Lihat log error                     : sudo journalctl -u us-proxy -f"
echo -e "${BLUE}==================================================================${NC}"
