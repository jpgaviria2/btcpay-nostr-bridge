# BTCPay to Nostr Bridge

A service that automatically publishes NIP-57 compliant zap receipts to Nostr when BTCPay Server invoices are settled. Supports dynamic multi-campaign fundraising with lightning addresses.

## Features

- 🔄 **Dynamic Campaign Discovery**: Automatically loads fundraising campaigns (kind 9041 events) from your Nostr relay
- ⚡ **Lightning Address Routing**: Routes donations to the correct campaign based on the lightning address used
- 📡 **NIP-57 Compliant**: Creates properly signed zap receipts with embedded zap requests
- 🔒 **Secure**: Webhook signature verification, all secrets in environment variables
- 🔁 **Production Ready**: Systemd service with auto-restart, duplicate detection, proper logging

## How It Works

1. User donates to a lightning address (e.g., `campaign@yourdomain.com`)
2. BTCPay Server creates invoice with the lightning address in metadata
3. When payment settles, BTCPay sends webhook to this service
4. Service:
   - Validates webhook signature
   - Fetches full invoice details from BTCPay API
   - Extracts lightning address from payment method data
   - Looks up corresponding campaign from Nostr relay
   - Creates NIP-57 zap receipt with proper signatures
   - Publishes to Nostr relay using nak CLI

## Requirements

- Python 3.8+
- BTCPay Server with API access
- Nostr relay
- `nak` CLI tool installed
- Systemd (for service management)

## Installation

### 1. Clone Repository

```bash
cd ~
git clone https://github.com/yourusername/btcpay-nostr-bridge.git
cd btcpay-nostr-bridge
```

### 2. Run Installation Script

```bash
sudo bash install.sh
```

This installs:
- Python virtual environment
- Required Python packages
- System dependencies

### 3. Install nak CLI

```bash
# Download and install nak
cd /tmp
wget https://github.com/fiatjaf/nak/releases/download/v0.7.5/nak-v0.7.5-linux-amd64
sudo mv nak-v0.7.5-linux-amd64 /usr/local/bin/nak
sudo chmod +x /usr/local/bin/nak
```

### 4. Configure Environment

```bash
cd ~/btcpay-nostr-bridge
cp .env.example .env
nano .env
```

Fill in all required values:

```bash
# Nostr Configuration
NOSTR_PRIVATE_KEY=nsec1... or hex_private_key
NOSTR_RELAY_URL=wss://your-relay.com

# Campaign Configuration
CAMPAIGN_REFRESH_INTERVAL=300  # seconds (5 minutes)

# BTCPay Configuration
BTCPAY_WEBHOOK_SECRET=your_webhook_secret_here
BTCPAY_SERVER_URL=https://your-btcpay-server.com
BTCPAY_API_KEY=your_api_key_here

# Service Configuration
WEBHOOK_PORT=8765
WEBHOOK_HOST=0.0.0.0
DEBUG=false
```

### 5. Setup Systemd Service

```bash
# Copy and customize the service template
cp btcpay-nostr-bridge.service.template btcpay-nostr-bridge.service
nano btcpay-nostr-bridge.service

# Update these values:
# - User=YOUR_USERNAME
# - Group=YOUR_USERNAME
# - WorkingDirectory=/path/to/btcpay-nostr-bridge
# - Update all paths to match your installation

# Install the service
sudo cp btcpay-nostr-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable btcpay-nostr-bridge
sudo systemctl start btcpay-nostr-bridge
```

### 6. Configure BTCPay Server

#### Create API Key

Your API key needs the `btcpay.store.canviewinvoices` permission:

1. Log into BTCPay Server
2. Go to Account → Manage Account → API Keys
3. Create new API key with permission: `btcpay.store.canviewinvoices:YOUR_STORE_ID`
4. Copy the key to your `.env` file

#### Configure Webhook

1. In BTCPay Server, go to your store → Settings → Webhooks
2. Add webhook:
   - **Payload URL**: `https://your-domain.com/btcpay-webhook`
   - **Secret**: Generate a random secret and add to `.env`
   - **Events**: Select "Invoice Settled" (InvoiceSettled)
   - **Automatic redelivery**: Enabled (optional)

#### Configure Reverse Proxy

If BTCPay is in Docker, you need to proxy the webhook URL:

```nginx
# Example Caddy config
handle /btcpay-webhook {
    reverse_proxy localhost:8765
}
```

### 7. Create Fundraising Campaigns

Publish kind 9041 fundraising events to your Nostr relay with these tags:

```json
{
  "kind": 9041,
  "content": "Campaign description",
  "tags": [
    ["title", "Your Campaign Name"],
    ["summary", "Short description"],
    ["image", "https://..."],
    ["amount", "1000000", "sats"],
    ["zap", "campaign@yourdomain.com"]
  ]
}
```

The service will automatically discover campaigns from your relay every 5 minutes.

## Usage

### Check Service Status

```bash
sudo systemctl status btcpay-nostr-bridge
```

### View Logs

```bash
# Live logs
sudo journalctl -u btcpay-nostr-bridge -f

# Recent logs
sudo journalctl -u btcpay-nostr-bridge -n 100
```

### Restart Service

```bash
sudo systemctl restart btcpay-nostr-bridge
```

### Test Payment Flow

1. Create invoice with lightning address in BTCPay
2. Pay the invoice
3. Check logs to see the zap receipt publication
4. Query your relay for kind 9735 events

## Project Structure

```
btcpay-nostr-bridge/
├── service.py              # Main Flask webhook server
├── config.py               # Configuration management
├── btcpay_client.py        # BTCPay API client
├── nostr_client.py         # Nostr event creation & publishing
├── campaign_manager.py     # Dynamic campaign discovery
├── requirements.txt        # Python dependencies
├── install.sh              # Installation script
├── .env.example            # Environment template
├── .gitignore             # Git ignore rules
└── btcpay-nostr-bridge.service.template  # Systemd service template
```

## Security

- ✅ All secrets stored in `.env` file (not in git)
- ✅ Webhook signature verification (HMAC-SHA256)
- ✅ Systemd security hardening enabled
- ✅ Read-only file system access
- ✅ No new privileges allowed

## Troubleshooting

### Service won't start

```bash
# Check logs for errors
sudo journalctl -u btcpay-nostr-bridge -n 50

# Validate configuration
cd ~/btcpay-nostr-bridge
source venv/bin/activate
python3 -c "from config import Config; Config.validate()"
```

### Webhooks not received

- Check reverse proxy configuration
- Verify webhook URL is accessible from BTCPay
- Check BTCPay webhook delivery logs
- Verify webhook secret matches in both places

### Events not publishing to relay

- Check nak is installed: `which nak`
- Test nak manually: `echo '{"kind":1,"content":"test"}' | nak event wss://your-relay.com`
- Check relay URL in `.env`
- Check relay accepts your events

### Duplicate events

- Ensure BTCPay webhook is configured for "InvoiceSettled" only
- Check service logs for "already processed" messages

## Contributing

Issues and pull requests welcome!

## License

MIT License - see LICENSE file for details
