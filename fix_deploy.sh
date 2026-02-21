#!/bin/bash
# ======================================================
# SheerID Platinum Bot — Fix & Deploy Script
# Jalankan ini di VPS untuk memperbaiki & restart bot
# ======================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="$HOME/SheerID-Verification-Tool-Platinum"
SERVICE_NAME="sheerid-bot"

echo -e "${BLUE}======================================================${NC}"
echo -e "${GREEN}   SheerID Platinum — Fix & Deploy${NC}"
echo -e "${BLUE}======================================================${NC}"
echo ""

# --- Step 1: Masuk ke direktori ---
if [ ! -d "$INSTALL_DIR" ]; then
  echo -e "${RED}[✗] Folder tidak ditemukan: $INSTALL_DIR${NC}"
  echo "    Jalankan install.sh terlebih dahulu."
  exit 1
fi
cd "$INSTALL_DIR" || exit 1
echo -e "${GREEN}[✓] Direktori: $INSTALL_DIR${NC}"

# --- Step 2: Bunuh proses lama yang mungkin masih jalan ---
echo -e "${YELLOW}[→] Membersihkan proses bot lama...${NC}"
pkill -f "python.*telegram_bot.py" 2>/dev/null && echo "    Proses lama dihentikan." || echo "    Tidak ada proses lama."

# --- Step 3: Reset perubahan lokal lalu pull kode terbaru ---
echo -e "${YELLOW}[→] Mengambil kode terbaru dari GitHub...${NC}"
git fetch origin main
git reset --hard origin/main
git pull origin main
echo -e "${GREEN}[✓] Kode berhasil diperbarui.${NC}"

# --- Step 4: Pastikan .env ada ---
if [ ! -f "$INSTALL_DIR/.env" ]; then
  echo -e "${RED}[✗] File .env tidak ditemukan!${NC}"
  echo ""
  echo "Buat file .env dulu dengan perintah:"
  echo ""
  echo "  nano $INSTALL_DIR/.env"
  echo ""
  echo "Isi dengan:"
  echo "  TELEGRAM_BOT_TOKEN=<token_dari_botfather>"
  echo "  PROXY_URL=http://user:pass@host:port"
  echo "  TELEGRAM_ADMIN_ID=<id_telegram_kamu>"
  echo ""
  exit 1
fi
echo -e "${GREEN}[✓] File .env ditemukan.${NC}"

# --- Step 5: Install / update dependencies ---
echo -e "${YELLOW}[→] Memperbarui library Python...${NC}"
source "$INSTALL_DIR/.venv/bin/activate"
pip install -q -r requirements.txt
echo -e "${GREEN}[✓] Library siap.${NC}"

# --- Step 6: Test syntax bot ---
echo -e "${YELLOW}[→] Mengecek syntax bot...${NC}"
python3 -c "import telegram_bot; print('Syntax OK')" 2>&1
if [ $? -ne 0 ]; then
  echo -e "${RED}[✗] Ada error syntax di telegram_bot.py! Lihat pesan di atas.${NC}"
  exit 1
fi
echo -e "${GREEN}[✓] Syntax aman.${NC}"

# --- Step 7: Reload & restart service ---
echo -e "${YELLOW}[→] Merestart service bot...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" 2>/dev/null
sudo systemctl restart "$SERVICE_NAME"
sleep 2

# --- Step 8: Cek status ---
STATUS=$(sudo systemctl is-active "$SERVICE_NAME" 2>/dev/null)
if [ "$STATUS" = "active" ]; then
  echo -e "${GREEN}[✓] Bot AKTIF dan berjalan! Status: $STATUS${NC}"
else
  echo -e "${RED}[✗] Bot tidak aktif. Status: $STATUS${NC}"
  echo ""
  echo "Lihat log error dengan:"
  echo "  sudo journalctl -u $SERVICE_NAME -n 30 --no-pager"
fi

echo ""
echo -e "${BLUE}======================================================${NC}"
echo -e "${GREEN} Selesai! Coba kirim /start ke bot kamu.${NC}"
echo -e "${BLUE}======================================================${NC}"
echo ""
echo "Perintah berguna:"
echo "  Lihat log live  : sudo journalctl -u $SERVICE_NAME -f"
echo "  Restart manual  : sudo systemctl restart $SERVICE_NAME"
echo "  Hentikan bot    : sudo systemctl stop $SERVICE_NAME"
