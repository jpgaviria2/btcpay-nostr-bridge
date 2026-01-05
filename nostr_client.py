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
    
    async def create_zap_receipt(self, amount_sats, invoice_id=None, bolt11=None, preimage=None):
        """
        Create a kind 9735 zap receipt event
        
        Args:
            amount_sats: Amount in satoshis
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
            
            # Link to fundraising campaign event
            tags.append(Tag.parse(["e", Config.CAMPAIGN_EVENT_ID]))
            
            # Link to campaign creator
            tags.append(Tag.parse(["p", Config.CAMPAIGN_CREATOR_PUBKEY]))
            
            # Amount in millisatoshis
            tags.append(Tag.parse(["amount", str(amount_msats)]))
            
            # Optional: Add bolt11 invoice
            if bolt11:
                tags.append(Tag.parse(["bolt11", bolt11]))
            
            # Optional: Add payment preimage as proof
            if preimage:
                tags.append(Tag.parse(["preimage", preimage]))
            
            # Optional: Add description with BTCPay invoice ID
            description_parts = []
            if invoice_id:
                description_parts.append(f"BTCPay Invoice: {invoice_id}")
            if amount_sats:
                description_parts.append(f"{amount_sats} sats donated")
            
            content = " | ".join(description_parts) if description_parts else ""
            
            # Build event
            event_builder = EventBuilder(Kind(9735), content).tags(tags)
            event = await event_builder.sign(self.signer)
            
            print(f"[Nostr] Created zap receipt event:")
            print(f"  Event ID: {event.id().to_hex()}")
            print(f"  Amount: {amount_sats} sats ({amount_msats} msats)")
            print(f"  Campaign: {Config.CAMPAIGN_EVENT_ID[:16]}...")
            print(f"  Creator: {Config.CAMPAIGN_CREATOR_PUBKEY[:16]}...")
            
            return event
            
        except Exception as e:
            print(f"[Nostr] Error creating event: {e}")
            raise
    
    async def publish_event(self, event):
        """
        Publish event to Nostr relay

        Args:
            event: Event object to publish

        Returns:
            bool: True if published successfully
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.debug(f"Sending event to relay...")
            result = await self.client.send_event(event)
            logger.info(f"✅ Published event: {result.id.to_hex()}")
            logger.debug(f"Success relays: {len(result.success)}, Failed relays: {len(result.failed)}")
            return True
        except Exception as e:
            logger.error(f"❌ Error publishing event: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def publish_donation(self, amount_sats, invoice_id=None, bolt11=None, preimage=None):
        """
        Create and publish a zap receipt for a donation

        Args:
            amount_sats: Amount in satoshis
            invoice_id: BTCPay invoice ID (optional)
            bolt11: Lightning invoice (optional)
            preimage: Payment preimage (optional)

        Returns:
            bool: True if published successfully
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.info(f"Creating zap receipt for {amount_sats} sats")
            # Create zap receipt event
            event = await self.create_zap_receipt(
                amount_sats=amount_sats,
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

