#!/bin/bash
# Installation script for BTCPay to Nostr Bridge
set -e

echo "=========================================="
echo "BTCPay to Nostr Bridge - Installation"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "This script requires sudo privileges."
    echo "Please run: sudo bash install.sh"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-$USER}
SERVICE_DIR="/home/$ACTUAL_USER/btcpay-nostr-bridge"

echo "Installing system dependencies..."
apt update
apt install -y python3-pip python3-venv python3-websockets

echo ""
echo "Creating Python virtual environment..."
cd "$SERVICE_DIR"
sudo -u $ACTUAL_USER python3 -m venv venv

echo ""
echo "Installing Python dependencies..."
sudo -u $ACTUAL_USER bash -c "source venv/bin/activate && pip install -r requirements.txt"

echo ""
echo "Configuring systemd service..."
cp btcpay-nostr-bridge.service /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Find your campaign details:"
echo "   cd $SERVICE_DIR"
echo "   source venv/bin/activate"
echo "   python3 setup_query_campaign.py"
echo ""
echo "2. Configure environment:"
echo "   cp .env.example .env"
echo "   nano .env"
echo "   # Fill in all required values"
echo ""
echo "3. Start the service:"
echo "   systemctl enable btcpay-nostr-bridge"
echo "   systemctl start btcpay-nostr-bridge"
echo ""
echo "4. Check status:"
echo "   systemctl status btcpay-nostr-bridge"
echo "   journalctl -u btcpay-nostr-bridge -f"
echo ""

