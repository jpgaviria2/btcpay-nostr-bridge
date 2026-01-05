#!/usr/bin/env python3
"""
BTCPay to Nostr Bridge Service
Receives BTCPay webhook notifications and publishes Nostr zap receipts
"""
import hmac
import hashlib
import json
import asyncio
import logging
import sys
from flask import Flask, request, jsonify
from config import Config
from nostr_client import NostrClient
from btcpay_client import BTCPayClient

# Set up logging to stderr (captured by systemd)
logging.basicConfig(
    level=logging.DEBUG if Config.DEBUG else logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize clients (will be set in main)
nostr_client = None
btcpay_client = None

def verify_webhook_signature(payload, signature, secret):
    """
    Verify BTCPay webhook signature using HMAC-SHA256
    
    Args:
        payload: Raw request body
        signature: Signature from BTCPay (sha256=...)
        secret: Webhook secret
    
    Returns:
        bool: True if signature is valid
    """
    if not signature:
        return False
    
    # BTCPay sends signature as "sha256=HEXDIGEST"
    if signature.startswith('sha256='):
        signature = signature[7:]
    
    # Calculate expected signature
    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected, signature)

def extract_invoice_data(webhook_data):
    """
    Extract relevant data from BTCPay webhook payload
    
    Args:
        webhook_data: Parsed JSON webhook data
    
    Returns:
        dict: Extracted invoice data
    """
    try:
        # BTCPay webhook structure varies by event type
        # For InvoiceSettled event, structure is typically:
        # {
        #   "type": "InvoiceSettled",
        #   "deliveryId": "...",
        #   "webhookId": "...",
        #   "originalDeliveryId": "...",
        #   "isRedelivery": false,
        #   "storeId": "...",
        #   "invoiceId": "...",
        #   ...additional invoice data...
        # }
        
        event_type = webhook_data.get('type', '')
        invoice_id = webhook_data.get('invoiceId', '')
        
        # Get amount - can be in different places depending on webhook version
        amount_sats = 0
        
        # Try to get amount from various possible locations
        if 'amount' in webhook_data:
            amount_sats = int(float(webhook_data['amount']))
        elif 'cryptoAmount' in webhook_data:
            amount_sats = int(float(webhook_data['cryptoAmount']) * 100000000)  # BTC to sats
        elif 'price' in webhook_data:
            # This might be in fiat, we'd need the crypto field
            pass
        
        # Try to get payment method details
        payment_method = webhook_data.get('paymentMethod', '')
        bolt11 = None
        preimage = None
        
        # Check for Lightning payment details
        if 'paymentMethodDetails' in webhook_data:
            pm_details = webhook_data.get('paymentMethodDetails', {})
            bolt11 = pm_details.get('lightningInvoice') or pm_details.get('BOLT11')
            preimage = pm_details.get('preimage')
        
        # Also check top-level fields
        if not bolt11:
            bolt11 = webhook_data.get('lightningInvoice') or webhook_data.get('BOLT11')
        if not preimage:
            preimage = webhook_data.get('preimage')
        
        return {
            'event_type': event_type,
            'invoice_id': invoice_id,
            'amount_sats': amount_sats,
            'bolt11': bolt11,
            'preimage': preimage,
            'payment_method': payment_method,
            'raw_data': webhook_data
        }
        
    except Exception as e:
        print(f"[Webhook] Error extracting invoice data: {e}")
        return None

@app.route('/btcpay-webhook', methods=['POST'])
def handle_btcpay_webhook():
    """Handle incoming BTCPay webhook"""
    logger.info("🔄 Received webhook request")
    try:
        # Get raw payload for signature verification
        raw_payload = request.get_data()
        logger.debug(f"📦 Payload length: {len(raw_payload)} bytes")

        # Get signature from header
        signature = request.headers.get('BTCPay-Sig')
        logger.debug(f"🔐 Signature: {signature}")

        # Verify signature
        if not verify_webhook_signature(raw_payload, signature, Config.BTCPAY_WEBHOOK_SECRET):
            logger.warning("❌ Invalid webhook signature")
            return jsonify({'error': 'Invalid signature'}), 401

        logger.info("✅ Signature verified")
        
        # Parse JSON payload
        webhook_data = request.get_json()
        
        if Config.DEBUG:
            print("[Webhook] Received webhook:")
            print(json.dumps(webhook_data, indent=2))
        
        # Extract invoice data
        invoice_data = extract_invoice_data(webhook_data)
        
        if not invoice_data:
            print("[Webhook] ❌ Failed to extract invoice data")
            return jsonify({'error': 'Invalid webhook data'}), 400
        
        # Check if this is an InvoiceSettled event
        if invoice_data['event_type'] != 'InvoiceSettled':
            logger.info(f"Ignoring event type: {invoice_data['event_type']}")
            return jsonify({'status': 'ignored', 'reason': 'Not an InvoiceSettled event'}), 200

        # Check if we have an amount
        if invoice_data['amount_sats'] <= 0:
            logger.warning(f"⚠️ Amount not in webhook, fetching from BTCPay API...")
            
            # Try to fetch invoice details from BTCPay
            store_id = webhook_data.get('storeId')
            if store_id and invoice_data['invoice_id']:
                full_invoice = btcpay_client.get_invoice(store_id, invoice_data['invoice_id'])
                
                if full_invoice:
                    logger.debug(f"[BTCPay] Full invoice data received")
                    # Extract amount from the full invoice data
                    invoice_data['amount_sats'] = btcpay_client.extract_amount_from_invoice(full_invoice)
                    logger.info(f"✅ Extracted amount: {invoice_data['amount_sats']} sats")
                else:
                    logger.error(f"❌ Could not fetch invoice from BTCPay API")
                    return jsonify({'error': 'Could not fetch invoice details'}), 500
            else:
                logger.error(f"❌ Missing storeId or invoiceId")
                return jsonify({'error': 'Invalid webhook data'}), 400
        
        # Final amount validation
        if invoice_data['amount_sats'] <= 0:
            logger.warning(f"❌ Invalid amount after API fetch: {invoice_data['amount_sats']}")
            return jsonify({'error': 'Invalid amount'}), 400

        logger.info(f"✅ Processing settled invoice: {invoice_data['invoice_id']}")
        logger.info(f"    Amount: {invoice_data['amount_sats']} sats")
        logger.info(f"    Payment Method: {invoice_data['payment_method']}")

        # Publish to Nostr (async operation)
        logger.info("📡 Publishing to Nostr...")
        success = asyncio.run(nostr_client.publish_donation(
            amount_sats=invoice_data['amount_sats'],
            invoice_id=invoice_data['invoice_id'],
            bolt11=invoice_data['bolt11'],
            preimage=invoice_data['preimage']
        ))

        if success:
            logger.info("✅ Donation successfully published to Nostr")
        else:
            logger.error("❌ Failed to publish donation to Nostr")

        return jsonify({
            'status': 'success',
            'message': 'Donation published to Nostr',
            'invoice_id': invoice_data['invoice_id'],
            'amount_sats': invoice_data['amount_sats']
        }), 200
        
    except Exception as e:
        print(f"[Webhook] ❌ Error handling webhook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'btcpay-nostr-bridge',
        'relay': Config.NOSTR_RELAY_URL,
        'campaign_configured': bool(Config.CAMPAIGN_EVENT_ID)
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Root endpoint with service info"""
    return jsonify({
        'service': 'BTCPay to Nostr Bridge',
        'version': '1.0.0',
        'endpoints': {
            'webhook': '/btcpay-webhook (POST)',
            'health': '/health (GET)'
        },
        'relay': Config.NOSTR_RELAY_URL,
        'campaign': Config.CAMPAIGN_EVENT_ID[:16] + '...' if Config.CAMPAIGN_EVENT_ID else 'Not configured'
    }), 200

async def initialize_nostr():
    """Initialize and connect Nostr client"""
    global nostr_client
    
    try:
        print("[Service] Initializing Nostr client...")
        nostr_client = NostrClient()
        await nostr_client.connect()
        print("[Service] ✅ Nostr client connected")
        return True
    except Exception as e:
        print(f"[Service] ❌ Failed to initialize Nostr client: {e}")
        return False

def main():
    """Main entry point"""
    global btcpay_client
    
    print("=" * 80)
    print("BTCPay to Nostr Bridge Service")
    print("=" * 80)
    
    # Print configuration
    Config.print_config()
    
    # Validate configuration
    try:
        Config.validate()
        print("[Service] ✅ Configuration validated")
    except ValueError as e:
        print(f"[Service] ❌ Configuration error: {e}")
        print("\nPlease check your .env file and ensure all required variables are set.")
        return 1
    
    # Initialize BTCPay client
    print("[Service] Initializing BTCPay client...")
    btcpay_client = BTCPayClient(
        server_url=Config.BTCPAY_SERVER_URL,
        api_key=Config.BTCPAY_API_KEY if Config.BTCPAY_API_KEY else None
    )
    print(f"[Service] ✅ BTCPay client initialized ({Config.BTCPAY_SERVER_URL})")
    
    # Initialize Nostr client
    if not asyncio.run(initialize_nostr()):
        print("[Service] ❌ Failed to initialize, exiting")
        return 1
    
    # Start Flask server
    print(f"\n[Service] Starting webhook server on {Config.WEBHOOK_HOST}:{Config.WEBHOOK_PORT}")
    print(f"[Service] Webhook URL: https://anmore.cash/btcpay-webhook")
    print("[Service] Press Ctrl+C to stop\n")
    
    try:
        app.run(
            host=Config.WEBHOOK_HOST,
            port=Config.WEBHOOK_PORT,
            debug=Config.DEBUG
        )
    except KeyboardInterrupt:
        print("\n[Service] Shutting down...")
        asyncio.run(nostr_client.close())
        print("[Service] Goodbye!")
    
    return 0

if __name__ == '__main__':
    exit(main())

