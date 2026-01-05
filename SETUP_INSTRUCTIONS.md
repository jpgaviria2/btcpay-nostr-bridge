# Setup Instructions - BTCPay to Nostr Bridge

## Status: Ready for Configuration

All code is installed and configured. You now need to complete 3 steps to make it operational:

---

## Step 1: Add Your Nostr Private Key

Edit the `.env` file and add your Nostr private key:

```bash
cd /home/btcpay/btcpay-nostr-bridge
nano .env
```

Find this line:
```
NOSTR_PRIVATE_KEY=YOUR_PRIVATE_KEY_HERE
```

Replace `YOUR_PRIVATE_KEY_HERE` with your actual Nostr private key (nsec format or hex).

**Example:**
```
NOSTR_PRIVATE_KEY=nsec1abc123xyz...
```

Save and exit (Ctrl+X, then Y, then Enter).

---

## Step 2: Configure BTCPay Webhook

### A. Access BTCPay Server

1. Open your browser and go to: `https://anmore.cash`
2. Log into BTCPay Server
3. Navigate to: **Store Settings** → **Webhooks**

### B. Create New Webhook

Click **"Create Webhook"** and configure:

| Field | Value |
|-------|-------|
| **Payload URL** | `https://anmore.cash/btcpay-webhook` |
| **Events** | ☑ Check **"InvoiceSettled"** only |
| **Secret** | Click **"Generate"** button |
| **Content Type** | `application/json` |
| **Enabled** | ☑ Checked |

### C. Save Webhook Secret

1. After clicking "Generate", copy the webhook secret (it will look like a long random string)
2. Edit your `.env` file again:

```bash
nano .env
```

3. Find this line:
```
BTCPAY_WEBHOOK_SECRET=YOUR_WEBHOOK_SECRET_HERE
```

4. Replace `YOUR_WEBHOOK_SECRET_HERE` with the secret you copied

**Example:**
```
BTCPAY_WEBHOOK_SECRET=9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b
```

5. Save and exit (Ctrl+X, then Y, then Enter)

6. Click **"Save"** in BTCPay to create the webhook

---

## Step 3: Start the Service

### A. Enable and Start

```bash
sudo systemctl enable btcpay-nostr-bridge
sudo systemctl start btcpay-nostr-bridge
```

### B. Check Status

```bash
sudo systemctl status btcpay-nostr-bridge
```

You should see:
- ✅ `Active: active (running)`
- ✅ No error messages

### C. Watch Logs

```bash
sudo journalctl -u btcpay-nostr-bridge -f
```

You should see:
```
[Service] ✅ Configuration validated
[Nostr] Initialized with pubkey: 17c122...
[Nostr] Connected to relay
[Service] Starting webhook server on 127.0.0.1:8765
```

Press Ctrl+C to stop watching logs.

---

## Step 4: Test the Integration

### A. Create Test Invoice

1. In BTCPay Server, create a test invoice (even for a small amount)
2. Pay the invoice (you can use your own Lightning wallet)
3. Wait for the invoice to be marked as "Settled"

### B. Watch for Webhook

Monitor the logs while paying:

```bash
sudo journalctl -u btcpay-nostr-bridge -f
```

You should see:
```
[Webhook] ✅ Processing settled invoice: INV123...
[Webhook]    Amount: 1000 sats
[Nostr] Created zap receipt event:
[Nostr]   Event ID: abc123...
[Nostr]   Amount: 1000 sats (1000000 msats)
[Nostr] ✅ Successfully published donation of 1000 sats
```

### C. Verify on Website

1. Open: `https://trailscoffee.com/fundraiser.html`
2. You should see the progress bar update in real-time
3. The donation amount should increment

---

## Configuration Summary

Your service is configured for:

- **Campaign**: Trails Coffee PAC Fundraiser
- **Campaign ID**: `38ae8cfd...` (most recent)
- **Lightning Address**: pac@anmore.cash
- **Webhook URL**: `https://anmore.cash/btcpay-webhook`
- **Relay**: `wss://relay.anmore.me`
- **Service Port**: 8765 (localhost only)

---

## Troubleshooting

### Service Won't Start

**Check configuration:**
```bash
cd /home/btcpay/btcpay-nostr-bridge
source venv/bin/activate
python3 service.py
```

This will show specific configuration errors.

**Common issues:**
- Missing Nostr private key
- Invalid private key format
- Missing webhook secret

### Webhook Not Received

**Test webhook endpoint:**
```bash
curl https://anmore.cash/btcpay-webhook
```

Should return service info (not 404).

**Check BTCPay webhook deliveries:**
1. Go to Store Settings → Webhooks
2. Click on your webhook
3. View "Recent Deliveries"
4. Check for failures

**Verify Caddy configuration:**
```bash
sudo cat /etc/caddy/Caddyfile | grep -A5 "btcpay-webhook"
```

Should show:
```
handle /btcpay-webhook {
    reverse_proxy localhost:8765
}
```

### Events Not Publishing to Nostr

**Test relay connection:**
```bash
cd /home/btcpay/btcpay-nostr-bridge
source venv/bin/activate
python3 << 'EOF'
import asyncio
from nostr_client import NostrClient

async def test():
    client = NostrClient()
    await client.connect()
    print("✅ Connected to relay!")
    await client.close()

asyncio.run(test())
EOF
```

**Verify private key:**
- Must be in nsec format (starts with "nsec1")
- Or hex format (64 character hex string)

### Website Not Updating

**Check fundraiser page:**
1. Open browser dev console (F12)
2. Visit: `https://trailscoffee.com/fundraiser.html`
3. Look for console logs showing zap events being received

**Query relay directly:**
```bash
cd /home/btcpay/btcpay-nostr-bridge
source venv/bin/activate
python3 << 'EOF'
import asyncio
import websockets
import json

async def check_zaps():
    uri = "wss://relay.anmore.me"
    async with websockets.connect(uri) as ws:
        # Query for zap receipts
        req = ["REQ", "test", {"kinds": [9735], "limit": 5}]
        await ws.send(json.dumps(req))
        
        for i in range(10):
            msg = await ws.recv()
            data = json.loads(msg)
            if data[0] == "EVENT":
                print(f"Found zap: {data[2]['id'][:16]}...")
            elif data[0] == "EOSE":
                break

asyncio.run(check_zaps())
EOF
```

---

## Useful Commands

### Service Management

```bash
# Start service
sudo systemctl start btcpay-nostr-bridge

# Stop service
sudo systemctl stop btcpay-nostr-bridge

# Restart service
sudo systemctl restart btcpay-nostr-bridge

# View status
sudo systemctl status btcpay-nostr-bridge

# Enable auto-start on boot
sudo systemctl enable btcpay-nostr-bridge

# Disable auto-start
sudo systemctl disable btcpay-nostr-bridge
```

### Logging

```bash
# Real-time logs
sudo journalctl -u btcpay-nostr-bridge -f

# Last 50 lines
sudo journalctl -u btcpay-nostr-bridge -n 50

# Logs since today
sudo journalctl -u btcpay-nostr-bridge --since today

# Logs from last hour
sudo journalctl -u btcpay-nostr-bridge --since "1 hour ago"
```

### Health Check

```bash
# Test local endpoint
curl http://localhost:8765/health

# Test public endpoint
curl https://anmore.cash/btcpay-webhook
```

---

## Security Notes

- `.env` file has restricted permissions (600 - owner only)
- Service listens only on localhost (not exposed directly)
- Caddy provides HTTPS/TLS termination
- Webhook signatures are verified (HMAC-SHA256)
- All secrets are in `.env` file (not in code)

---

## Support

- **Logs**: `sudo journalctl -u btcpay-nostr-bridge -f`
- **Documentation**: `README.md` in this directory
- **Contact**: hello@trailscoffee.com

---

## Next Steps After Setup

1. Monitor the first few donations to ensure everything works
2. Consider setting up monitoring/alerting for service health
3. Backup your `.env` file securely (contains private keys!)
4. Test with different invoice amounts
5. Verify website updates in real-time

---

**Status**: 🟡 Awaiting Final Configuration (Steps 1-3 above)

Once you complete Steps 1-3, the service will be fully operational!

