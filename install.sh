#!/bin/bash

# Define Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${GREEN}   SheerID Verification Tool Platinum - Auto Installer${NC}"
echo -e "${BLUE}======================================================${NC}"
echo ""

echo -e "${YELLOW}[1/5] Meminta Informasi Konfigurasi Bot...${NC}"
echo -e "Silakan masukkan detail berikut dengan benar:"
read -p "1. TELEGRAM BOT TOKEN (dari BotFather) : " BOT_TOKEN
read -p "2. PROXY URL (http://user:pass@ip:port): " PROXY_URL
read -p "3. TELEGRAM ADMIN ID (berupa angka)    : " ADMIN_ID

if [ -z "$BOT_TOKEN" ] || [ -z "$PROXY_URL" ] || [ -z "$ADMIN_ID" ]; then
    echo -e "${RED}ERROR: Semua data wajib diisi! Instalasi dibatalkan.${NC}"
    exit 1
fi

INSTALL_DIR="$HOME/SheerID-Verification-Tool-Platinum"

echo ""
echo -e "${YELLOW}[2/5] Menginstal Dependensi Sistem (Python, Git, dll)...${NC}"
sudo apt update -y
sudo apt install -y git python3 python3-pip python3-venv curl

echo ""
echo -e "${YELLOW}[3/5] Mengunduh Repository Utama...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo "Folder instalasi ditemukan. Melakukan update (git pull)..."
    cd "$INSTALL_DIR"
    git reset --hard HEAD
    git pull origin main
else
    git clone https://github.com/Timcuan/SheerID-Verification-Tool-Platinum.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo ""
echo -e "${YELLOW}[4/5] Mengatur Virtual Environment & Install Library...${NC}"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

echo ""
echo -e "${YELLOW}[5/5] Membuat File Konfigurasi Rahasia (.env)...${NC}"
cat <<EOF > .env
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
PROXY_URL=$PROXY_URL
TELEGRAM_ADMIN_ID=$ADMIN_ID
EOF
echo -e "${GREEN}.env sukses dibuat!${NC}"

echo ""
echo -e "${YELLOW}[+] Membuat Background Service (Bot Selalu Hidup 24/7)...${NC}"
SERVICE_FILE="/etc/systemd/system/sheerid-bot.service"

sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=SheerID Verification Telegram Bot Platinum
After=network.target

[Service]
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python telegram_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Reload and enable the service
sudo systemctl daemon-reload
sudo systemctl enable sheerid-bot
sudo systemctl restart sheerid-bot

echo ""
echo -e "${BLUE}======================================================${NC}"
echo -e "${GREEN} INSTALASI SELESAI & SUKSES! 🚀${NC}"
echo -e "${BLUE}======================================================${NC}"
echo -e "Bot Anda sekarang telah berjalan di background VPS secara absolut."
echo -e "Bahkan jika VPS di-restart, bot akan otomatis menyala sendiri!"
echo ""
echo -e "${YELLOW}[Panduan Manajemen Bot]${NC}"
echo -e " - Cek status bot  : ${GREEN}sudo systemctl status sheerid-bot${NC}"
echo -e " - Cek log/error   : ${GREEN}sudo journalctl -u sheerid-bot -f${NC} (Tekan Ctrl+C untuk keluar log)"
echo -e " - Merestart bot   : ${GREEN}sudo systemctl restart sheerid-bot${NC}"
echo -e " - Mematikan bot   : ${RED}sudo systemctl stop sheerid-bot${NC}"
echo -e "${BLUE}======================================================${NC}"
