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
from campaign_manager import CampaignManager

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
campaign_manager = None

# Track processed invoices to avoid duplicates
processed_invoices = set()

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

        # Log all headers for debugging
        logger.debug(f"📋 Headers: {dict(request.headers)}")

        # Get signature from header (try both casings)
        signature = request.headers.get('BTCPAY-SIG') or request.headers.get('BTCPay-Sig')
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
        
        # Accept any invoice event and check status from API
        logger.info(f"📨 Processing event: {invoice_data['event_type']}")

        # Fetch full invoice from BTCPay API to check status and get metadata
        logger.info("📡 Fetching invoice details from BTCPay API...")
        store_id = webhook_data.get('storeId')
        
        if not store_id or not invoice_data['invoice_id']:
            logger.error(f"❌ Missing storeId or invoiceId")
            return jsonify({'error': 'Invalid webhook data'}), 400
        
        full_invoice = btcpay_client.get_invoice(store_id, invoice_data['invoice_id'])
        
        if not full_invoice:
            logger.error(f"❌ Could not fetch invoice from BTCPay API")
            return jsonify({'error': 'Could not fetch invoice details'}), 500
        
        logger.debug(f"[BTCPay] Full invoice data received")
        
        # Check if invoice is settled
        invoice_status = full_invoice.get('status', '').lower()
        if invoice_status != 'settled':
            logger.info(f"⏳ Invoice not settled yet (status: {invoice_status}), ignoring")
            return jsonify({'status': 'ignored', 'reason': f'Invoice status is {invoice_status}, not settled'}), 200
        
        # Check if we've already processed this invoice (to avoid duplicates from multiple webhook events)
        if invoice_data['invoice_id'] in processed_invoices:
            logger.info(f"⏭️  Invoice {invoice_data['invoice_id']} already processed, skipping duplicate")
            return jsonify({'status': 'already_processed'}), 200
        
        # Mark invoice as processed
        processed_invoices.add(invoice_data['invoice_id'])
        
        # Also fetch payment methods to get lightning address from LNURL payments
        payment_methods = btcpay_client.get_invoice_payment_methods(store_id, invoice_data['invoice_id'])
        
        # Extract amount from full invoice if not in webhook
        if invoice_data['amount_sats'] <= 0:
            logger.debug("Extracting amount from API response...")
            invoice_data['amount_sats'] = btcpay_client.extract_amount_from_invoice(full_invoice)
        
        # Validate amount
        if invoice_data['amount_sats'] <= 0:
            logger.warning(f"❌ Invalid amount: {invoice_data['amount_sats']}")
            return jsonify({'error': 'Invalid amount'}), 400

        logger.info(f"✅ Processing settled invoice: {invoice_data['invoice_id']}")
        logger.info(f"    Amount: {invoice_data['amount_sats']} sats")
        logger.info(f"    Payment Method: {invoice_data['payment_method']}")

        # Extract lightning address from payment methods and invoice metadata
        logger.info("🔍 Extracting lightning address from invoice...")
        lightning_address = btcpay_client.extract_lightning_address_from_invoice(full_invoice, payment_methods)
        
        if not lightning_address:
            logger.error("❌ Could not determine lightning address for invoice")
            logger.error("   Invoice metadata must include 'lightningAddress' field")
            return jsonify({'error': 'No lightning address found in invoice'}), 400
        
        # Extract bolt11 and preimage from payment methods if available
        if payment_methods:
            for pm in payment_methods:
                if pm.get('paymentMethodId') in ['BTC-LNURL', 'BTC-LightningLike', 'BTC-LightningNetwork']:
                    # Get bolt11 from destination or payments
                    if not invoice_data['bolt11'] and 'destination' in pm:
                        invoice_data['bolt11'] = pm['destination']
                    
                    # Try to get from additionalData
                    additional_data = pm.get('additionalData', {})
                    if not invoice_data['bolt11'] and 'generatedBolt' in additional_data:
                        invoice_data['bolt11'] = additional_data['generatedBolt']
                    
                    # Get preimage if available
                    if not invoice_data['preimage'] and 'preimage' in additional_data:
                        invoice_data['preimage'] = additional_data['preimage']
                    
                    # Also check in payments array
                    payments = pm.get('payments', [])
                    if payments and len(payments) > 0:
                        payment = payments[0]  # Get first/latest payment
                        if not invoice_data['bolt11'] and 'destination' in payment:
                            invoice_data['bolt11'] = payment['destination']
        
        if invoice_data['bolt11']:
            logger.debug(f"   Found bolt11: {invoice_data['bolt11'][:50]}...")
        if invoice_data['preimage']:
            logger.debug(f"   Found preimage: {invoice_data['preimage'][:16]}...")
        
        logger.info(f"✅ Lightning address: {lightning_address}")
        
        # Lookup campaign by lightning address (optional - nice to have but not required)
        logger.info(f"🔍 Looking up campaign for {lightning_address}...")
        campaign = campaign_manager.get_campaign_by_lightning_address(lightning_address)
        
        campaign_event_id = None
        campaign_pubkey = None
        
        if campaign:
            logger.info(f"✅ Found campaign: {campaign.title}")
            logger.info(f"   Campaign ID: {campaign.event_id[:16]}...")
            logger.info(f"   Creator: {campaign.pubkey[:16]}...")
            campaign_event_id = campaign.event_id
            campaign_pubkey = campaign.pubkey
        else:
            logger.warning(f"⚠️  No campaign found for {lightning_address}, will publish basic receipt")
            logger.info("   Zap receipt will still be posted with lightning address for UI aggregation")

        # Publish to Nostr (async operation) - always publish, campaign data is optional
        logger.info("📡 Publishing zap receipt to Nostr...")
        success = asyncio.run(nostr_client.publish_donation(
            amount_sats=invoice_data['amount_sats'],
            lightning_address=lightning_address,
            campaign_event_id=campaign_event_id,
            campaign_pubkey=campaign_pubkey,
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
    campaign_count = campaign_manager.get_campaign_count() if campaign_manager else 0
    return jsonify({
        'status': 'healthy',
        'service': 'btcpay-nostr-bridge',
        'relay': Config.NOSTR_RELAY_URL,
        'campaign_mode': 'dynamic',
        'campaigns_loaded': campaign_count
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Root endpoint with service info"""
    campaign_count = campaign_manager.get_campaign_count() if campaign_manager else 0
    campaigns_list = []
    
    if campaign_manager:
        for ln_addr, campaign in campaign_manager.get_all_campaigns().items():
            campaigns_list.append({
                'lightning_address': ln_addr,
                'title': campaign.title,
                'event_id': campaign.event_id[:16] + '...'
            })
    
    return jsonify({
        'service': 'BTCPay to Nostr Bridge',
        'version': '2.0.0',
        'mode': 'dynamic',
        'endpoints': {
            'webhook': '/btcpay-webhook (POST)',
            'health': '/health (GET)'
        },
        'relay': Config.NOSTR_RELAY_URL,
        'campaigns': campaigns_list,
        'campaign_count': campaign_count
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

async def initialize_campaigns():
    """Initialize campaign manager and load campaigns"""
    global campaign_manager
    
    try:
        print("[Service] Initializing campaign manager...")
        campaign_manager = CampaignManager(Config.NOSTR_RELAY_URL)
        
        print("[Service] Loading campaigns from relay...")
        campaign_count = await campaign_manager.refresh_campaigns()
        
        if campaign_count == 0:
            print("[Service] ⚠️  WARNING: No campaigns found on relay!")
            print("[Service]     Ensure kind 9041 events exist with lightning address tags")
            print("[Service]     Service will start but won't process payments until campaigns are published")
        else:
            print(f"[Service] ✅ Loaded {campaign_count} campaign(s)")
        
        return True
    except Exception as e:
        print(f"[Service] ❌ Failed to initialize campaign manager: {e}")
        import traceback
        traceback.print_exc()
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
        print("[Service] ❌ Failed to initialize Nostr, exiting")
        return 1
    
    # Initialize campaign manager and load campaigns
    if not asyncio.run(initialize_campaigns()):
        print("[Service] ❌ Failed to initialize campaigns, exiting")
        return 1
    
    # Start Flask server
    print(f"\n[Service] Starting webhook server on {Config.WEBHOOK_HOST}:{Config.WEBHOOK_PORT}")
    print(f"[Service] Webhook URL: {Config.BTCPAY_SERVER_URL}/btcpay-webhook")
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

