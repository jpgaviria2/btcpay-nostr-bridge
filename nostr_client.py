"""
Nostr client for creating and publishing zap receipt events (kind 9735)
"""
import time
import json
from nostr_sdk import Keys, Client, EventBuilder, Event, Tag, Kind, RelayOptions, NostrSigner, RelayUrl
from config import Config

class NostrClient:
    """Handles Nostr event creation and publishing"""

    def __init__(self):
        """Initialize Nostr client with private key"""
        try:
            # Store relay URL
            self.relay_url = Config.NOSTR_RELAY_URL

            # Load keys from private key (nsec or hex format)
            if Config.NOSTR_PRIVATE_KEY.startswith('nsec'):
                self.keys = Keys.parse(Config.NOSTR_PRIVATE_KEY)
            else:
                # Assume hex format
                self.keys = Keys.from_sk_str(Config.NOSTR_PRIVATE_KEY)

            self.pubkey = self.keys.public_key()
            print(f"[Nostr] Initialized with pubkey: {self.pubkey.to_hex()[:16]}...")

            # Create signer from keys
            self.signer = NostrSigner.keys(self.keys)

            # Initialize client with signer
            self.client = Client(self.signer)

            print(f"[Nostr] Client initialized with signer")

        except Exception as e:
            print(f"[Nostr] Error initializing client: {e}")
            raise

    async def connect(self):
        """Connect to Nostr relays"""
        try:
            # Add relay first
            relay_url = RelayUrl.parse(Config.NOSTR_RELAY_URL)
            await self.client.add_relay(relay_url)
            print(f"[Nostr] Added relay: {Config.NOSTR_RELAY_URL}")

            # Then connect
            await self.client.connect()
            print("[Nostr] Connected to relay")
        except Exception as e:
            print(f"[Nostr] Error connecting: {e}")
            raise

    async def create_zap_receipt(self, amount_sats, campaign_event_id, campaign_pubkey,
                                 lightning_address=None, invoice_id=None, bolt11=None, preimage=None):
        """
        Create a kind 9735 zap receipt event

        Args:
            amount_sats: Amount in satoshis
            campaign_event_id: Fundraising campaign event ID (kind 9041)
            campaign_pubkey: Campaign creator's public key
            invoice_id: BTCPay invoice ID (optional)
            bolt11: Lightning invoice (optional)
            preimage: Payment preimage (optional)

        Returns:
            Event object
        """
        try:
            # Convert sats to millisats
            amount_msats = amount_sats * 1000

            # Build tags
            tags = []

            # REQUIRED: Lightning address for UI aggregation
            if lightning_address:
                tags.append(Tag.parse(["lnurl", lightning_address]))

            # Amount in millisatoshis (REQUIRED)
            tags.append(Tag.parse(["amount", str(amount_msats)]))

            # OPTIONAL: Link to fundraising campaign event if known
            if campaign_event_id:
                tags.append(Tag.parse(["e", campaign_event_id]))

            # OPTIONAL: Link to campaign creator if known
            if campaign_pubkey:
                tags.append(Tag.parse(["p", campaign_pubkey]))

            # REQUIRED: Add bolt11 invoice (NIP-57 requirement)
            if bolt11:
                tags.append(Tag.parse(["bolt11", bolt11]))
            else:
                print("[Nostr] WARNING: bolt11 is required for NIP-57 zap receipts")

            # Optional: Add payment preimage as proof
            if preimage:
                tags.append(Tag.parse(["preimage", preimage]))

            # Create a proper signed zap request event for the description tag (NIP-57)
            # This is optional but recommended for better compatibility
            import json
            zap_request_tags = []
            
            # Add campaign tags if available
            if campaign_event_id:
                zap_request_tags.append(Tag.parse(["e", campaign_event_id]))
            if campaign_pubkey:
                zap_request_tags.append(Tag.parse(["p", campaign_pubkey]))
            
            # Always include amount
            zap_request_tags.append(Tag.parse(["amount", str(amount_msats)]))
            
            # Build and sign the zap request (kind 9734)
            zap_request_builder = EventBuilder(Kind(9734), f"Donation of {amount_sats} sats").tags(zap_request_tags)
            zap_request_event = await zap_request_builder.sign(self.signer)
            
            # Serialize the signed event to JSON for the description tag  
            # Convert tags to list format
            tags_list = []
            for tag in zap_request_event.tags().to_vec():
                tags_list.append(tag.as_vec())
            
            zap_request_json = {
                "id": zap_request_event.id().to_hex(),
                "pubkey": zap_request_event.author().to_hex(),
                "created_at": zap_request_event.created_at().as_secs(),
                "kind": zap_request_event.kind().as_u16(),
                "tags": tags_list,
                "content": zap_request_event.content(),
                "sig": zap_request_event.signature()
            }
            
            # Add description tag with properly signed zap request
            tags.append(Tag.parse(["description", json.dumps(zap_request_json)]))

            # Content can describe the payment
            content_parts = []
            if invoice_id:
                content_parts.append(f"BTCPay Invoice: {invoice_id}")
            if amount_sats:
                content_parts.append(f"{amount_sats} sats donated")

            content = " | ".join(content_parts) if content_parts else ""

            # Build event
            event_builder = EventBuilder(Kind(9735), content).tags(tags)
            event = await event_builder.sign(self.signer)

            print(f"[Nostr] Created zap receipt event:")
            print(f"  Event ID: {event.id().to_hex()}")
            print(f"  Amount: {amount_sats} sats ({amount_msats} msats)")
            print(f"  Lightning Address: {lightning_address or 'unknown'}")
            if campaign_event_id:
                print(f"  Campaign: {campaign_event_id[:16]}...")
            if campaign_pubkey:
                print(f"  Creator: {campaign_pubkey[:16]}...")

            return event

        except Exception as e:
            print(f"[Nostr] Error creating event: {e}")
            raise

    async def publish_event(self, event):
        """
        Publish event to Nostr relay using nak CLI

        Args:
            event: Event object to publish

        Returns:
            bool: True if published successfully
        """
        import logging
        import subprocess
        import json
        from config import Config

        logger = logging.getLogger(__name__)

        try:
            logger.debug(f"Preparing event for nak CLI...")

            # Convert event to JSON
            tags_list = []
            for tag in event.tags().to_vec():
                tags_list.append(tag.as_vec())

            event_json = {
                "id": event.id().to_hex(),
                "pubkey": event.author().to_hex(),
                "created_at": event.created_at().as_secs(),
                "kind": event.kind().as_u16(),
                "tags": tags_list,
                "content": event.content(),
                "sig": event.signature()
            }

            event_str = json.dumps(event_json)

            # Use nak to publish the pre-signed event by piping it via stdin
            cmd = ['nak', 'event', self.relay_url]

            logger.debug(f"Publishing event {event_json['id'][:16]}... to {self.relay_url}")

            result = subprocess.run(
                cmd,
                input=event_str,
                capture_output=True,
                text=True,
                timeout=30
            )

            output = result.stdout + result.stderr
            logger.debug(f"nak output: {output}")

            if result.returncode == 0 and 'success' in output.lower():
                logger.info(f"✅ Published event: {event_json['id'][:16]}...")
                return True
            else:
                logger.error(f"❌ Event NOT published")
                logger.error(f"   Event ID: {event_json['id'][:16]}...")
                logger.error(f"   nak output: {output}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"❌ Timeout publishing event with nak")
            return False
        except Exception as e:
            logger.error(f"❌ Error publishing event: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    async def publish_donation(self, amount_sats, lightning_address, campaign_event_id=None, 
                              campaign_pubkey=None, invoice_id=None, bolt11=None, preimage=None):
        """
        Create and publish a zap receipt for a donation

        Args:
            amount_sats: Amount in satoshis (REQUIRED)
            lightning_address: Lightning address that was paid (REQUIRED)
            campaign_event_id: Fundraising campaign event ID (kind 9041) - optional
            campaign_pubkey: Campaign creator's public key - optional
            invoice_id: BTCPay invoice ID (optional)
            bolt11: Lightning invoice (optional)
            preimage: Payment preimage (optional)

        Returns:
            bool: True if published successfully
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.info(f"Creating zap receipt for {amount_sats} sats to {lightning_address}")
            # Create zap receipt event
            event = await self.create_zap_receipt(
                amount_sats=amount_sats,
                lightning_address=lightning_address,
                campaign_event_id=campaign_event_id,
                campaign_pubkey=campaign_pubkey,
                invoice_id=invoice_id,
                bolt11=bolt11,
                preimage=preimage
            )

            logger.info("Publishing event to relay...")
            # Publish to relay
            success = await self.publish_event(event)

            if success:
                logger.info(f"✅ Successfully published donation of {amount_sats} sats")
            else:
                logger.error("❌ Failed to publish donation - publish_event returned False")

            return success

        except Exception as e:
            logger.error(f"❌ Error publishing donation: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    async def close(self):
        """Close connections"""
        try:
            await self.client.disconnect()
            print("[Nostr] Disconnected from relay")
        except Exception as e:
            print(f"[Nostr] Error disconnecting: {e}")

