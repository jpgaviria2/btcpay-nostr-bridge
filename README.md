# BTCPay to Nostr Bridge Service

A lightweight service that bridges BTCPay Server invoice settlements to Nostr events, enabling real-time fundraising updates on your website.

## Overview

This service:
- Listens for BTCPay Server webhook notifications
- Validates webhook signatures for security
- Creates Nostr zap receipt events (kind 9735)
- Publishes events to relay.anmore.me
- Enables real-time donation tracking on your fundraising page

## Architecture

```
Donor → BTCPay Server → Webhook → This Service → Nostr Relay → Website
```

## Prerequisites

- Python 3.12 or higher
- BTCPay Server with webhook access
- Nostr private key (nsec format)
- Existing fundraising campaign (kind 9041 event) on relay.anmore.me
- Caddy web server (for proxying webhook URL)

## Installation

### 1. Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv
```

### 2. Create Virtual Environment

```bash
cd /home/btcpay/btcpay-nostr-bridge
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Find Your Campaign Details

Run the campaign query script to find your fundraising campaign:

```bash
python3 setup_query_campaign.py
```

This will output the `CAMPAIGN_EVENT_ID` and `CAMPAIGN_CREATOR_PUBKEY` values you need.

### 5. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
chmod 600 .env  # Secure the file
```

Edit `.env` and fill in all required values:

```bash
nano .env
```

Required variables:
- `NOSTR_PRIVATE_KEY`: Your Nostr private key (nsec format)
- `CAMPAIGN_EVENT_ID`: From step 4
- `CAMPAIGN_CREATOR_PUBKEY`: From step 4
- `BTCPAY_WEBHOOK_SECRET`: Get this from BTCPay (step 7)

### 6. Configure Caddy Reverse Proxy

Add this to your Caddy configuration (`/etc/caddy/Caddyfile`):

```caddy
anmore.cash {
    # BTCPay webhook endpoint
    handle /btcpay-webhook {
        reverse_proxy localhost:8765
    }
    
    # ... your other configuration ...
}
```

Reload Caddy:

```bash
sudo systemctl reload caddy
```

### 7. Set Up BTCPay Webhook

1. Log into BTCPay Server
2. Go to Store Settings → Webhooks
3. Click "Create Webhook"
4. Configure:
   - **Payload URL**: `https://anmore.cash/btcpay-webhook`
   - **Events**: Check "InvoiceSettled"
   - **Secret**: Click "Generate" and copy the value
   - **Content Type**: `application/json`
5. Save webhook
6. Add the secret to your `.env` file as `BTCPAY_WEBHOOK_SECRET`

### 8. Install Systemd Service

Copy the service file:

```bash
sudo cp btcpay-nostr-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Enable and start the service:

```bash
sudo systemctl enable btcpay-nostr-bridge
sudo systemctl start btcpay-nostr-bridge
```

Check status:

```bash
sudo systemctl status btcpay-nostr-bridge
```

## Usage

### View Logs

```bash
# Real-time logs
sudo journalctl -u btcpay-nostr-bridge -f

# Last 50 lines
sudo journalctl -u btcpay-nostr-bridge -n 50
```

### Restart Service

```bash
sudo systemctl restart btcpay-nostr-bridge
```

### Stop Service

```bash
sudo systemctl stop btcpay-nostr-bridge
```

### Test Health Endpoint

```bash
curl http://localhost:8765/health
```

### Test Webhook Manually

You can send a test webhook from BTCPay Server:

1. Go to Store Settings → Webhooks
2. Click on your webhook
3. Click "Recent Deliveries"
4. Create a test invoice and mark it as paid
5. Watch the logs: `sudo journalctl -u btcpay-nostr-bridge -f`

## Monitoring

### Service Health

```bash
systemctl status btcpay-nostr-bridge
```

### View Recent Donations

Query the relay for recent zap receipts:

```bash
# If you have nak installed
nak req -k 9735 wss://relay.anmore.me --limit 10

# Or use the Python script
python3 -c "import asyncio; from nostr_client import NostrClient; asyncio.run(NostrClient().connect())"
```

### Website Updates

Visit your fundraising page and watch donations appear in real-time:
- https://trailscoffee.com/fundraiser.html

## Troubleshooting

### Service Won't Start

Check configuration:
```bash
cd /home/btcpay/btcpay-nostr-bridge
source venv/bin/activate
python3 service.py
```

This will show any configuration errors.

### Webhooks Not Received

1. Check Caddy is proxying correctly:
   ```bash
   curl https://anmore.cash/btcpay-webhook
   ```

2. Check BTCPay webhook deliveries in dashboard

3. Verify webhook secret matches

### Events Not Publishing

1. Check Nostr relay is accessible:
   ```bash
   curl -I https://relay.anmore.me
   ```

2. Verify private key is correct

3. Check campaign event ID exists on relay

### Permission Issues

Ensure service file has correct user:
```bash
sudo nano /etc/systemd/system/btcpay-nostr-bridge.service
# User should be: btcpay
```

## Security Considerations

- `.env` file contains sensitive keys (chmod 600)
- Service listens only on localhost (not exposed to internet)
- Caddy provides TLS/HTTPS termination
- Webhook signatures are verified
- No authentication tokens stored in logs

## File Structure

```
/home/btcpay/btcpay-nostr-bridge/
├── service.py                    # Main webhook listener
├── nostr_client.py               # Nostr event creation & publishing
├── config.py                     # Configuration management
├── requirements.txt              # Python dependencies
├── .env                          # Configuration (create from .env.example)
├── .env.example                  # Configuration template
├── setup_query_campaign.py       # Helper to find campaign details
├── btcpay-nostr-bridge.service   # Systemd service file
└── README.md                     # This file
```

## Support

- Check logs: `journalctl -u btcpay-nostr-bridge -f`
- Verify configuration: Check `.env` file
- Test webhook: Use BTCPay's webhook test feature
- Contact: hello@trailscoffee.com

## License

MIT License - Feel free to use and modify for your needs.

