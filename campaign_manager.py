"""
Campaign Manager for dynamic fundraising campaign lookup
Queries relay for kind 9041 events and maps lightning addresses to campaigns
"""
import json
import asyncio
import websockets
import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CampaignInfo:
    """Information about a fundraising campaign"""
    event_id: str
    pubkey: str
    title: str
    lightning_address: str
    goal: Optional[int] = None
    summary: Optional[str] = None
    created_at: int = 0

class CampaignManager:
    """Manages fundraising campaigns from Nostr relay"""
    
    def __init__(self, relay_url: str):
        """
        Initialize campaign manager
        
        Args:
            relay_url: Nostr relay URL (e.g., wss://relay.anmore.me)
        """
        self.relay_url = relay_url
        self.campaigns = {}  # lightning_address -> CampaignInfo
        self.last_refresh = 0
        self.refresh_interval = 300  # 5 minutes
        
    async def refresh_campaigns(self) -> int:
        """
        Query relay for all kind 9041 fundraising events and rebuild campaign cache
        
        Returns:
            int: Number of campaigns loaded
        """
        logger.info(f"🔄 Refreshing campaigns from {self.relay_url}")
        
        try:
            async with websockets.connect(self.relay_url, timeout=10) as ws:
                # Subscribe to kind 9041 events
                subscription_id = "campaign_refresh"
                request = json.dumps([
                    "REQ",
                    subscription_id,
                    {
                        "kinds": [9041],
                        "limit": 100
                    }
                ])
                
                await ws.send(request)
                logger.debug("Sent REQ for kind 9041 events")
                
                new_campaigns = {}
                timeout_seconds = 10
                
                try:
                    async with asyncio.timeout(timeout_seconds):
                        while True:
                            response = await ws.recv()
                            data = json.loads(response)
                            
                            if data[0] == "EVENT":
                                event = data[2]
                                campaign_info = self._parse_campaign_event(event)
                                
                                if campaign_info and campaign_info.lightning_address:
                                    # Store with lowercase address for case-insensitive lookup
                                    ln_key = campaign_info.lightning_address.lower()
                                    new_campaigns[ln_key] = campaign_info
                                    logger.debug(f"Loaded campaign: {campaign_info.title} -> {ln_key}")
                            
                            elif data[0] == "EOSE":
                                # End of stored events
                                break
                
                except asyncio.TimeoutError:
                    logger.debug(f"Timeout after {timeout_seconds}s waiting for events")
                
                # Close subscription
                close_msg = json.dumps(["CLOSE", subscription_id])
                await ws.send(close_msg)
                
                # Update campaigns cache
                self.campaigns = new_campaigns
                self.last_refresh = time.time()
                
                logger.info(f"✅ Loaded {len(self.campaigns)} campaign(s)")
                
                # Log campaign details
                for ln_addr, campaign in self.campaigns.items():
                    logger.info(f"  📧 {ln_addr} → {campaign.title[:40]}")
                
                return len(self.campaigns)
                
        except Exception as e:
            logger.error(f"❌ Error refreshing campaigns: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return 0
    
    def _parse_campaign_event(self, event: Dict) -> Optional[CampaignInfo]:
        """
        Parse a kind 9041 event into CampaignInfo
        
        Args:
            event: Nostr event dict
            
        Returns:
            CampaignInfo or None if invalid
        """
        try:
            event_id = event.get('id')
            pubkey = event.get('pubkey')
            title = event.get('content', 'Untitled Campaign')
            created_at = event.get('created_at', 0)
            
            if not event_id or not pubkey:
                logger.warning(f"Invalid campaign event: missing id or pubkey")
                return None
            
            # Extract tags
            tags = event.get('tags', [])
            lightning_address = None
            goal = None
            summary = None
            
            for tag in tags:
                if len(tag) < 2:
                    continue
                
                tag_name = tag[0]
                tag_value = tag[1]
                
                # Check for lightning address (zap or lnaddress tag)
                if tag_name in ['zap', 'lnaddress']:
                    lightning_address = tag_value
                
                # Check for goal amount
                elif tag_name == 'amount':
                    try:
                        goal = int(tag_value)
                    except ValueError:
                        logger.warning(f"Invalid amount tag: {tag_value}")
                
                # Check for summary
                elif tag_name == 'summary':
                    summary = tag_value
            
            if not lightning_address:
                logger.warning(f"Campaign {event_id[:16]}... has no lightning address tag")
                return None
            
            return CampaignInfo(
                event_id=event_id,
                pubkey=pubkey,
                title=title,
                lightning_address=lightning_address,
                goal=goal,
                summary=summary,
                created_at=created_at
            )
            
        except Exception as e:
            logger.error(f"Error parsing campaign event: {e}")
            return None
    
    def get_campaign_by_lightning_address(self, lightning_address: str) -> Optional[CampaignInfo]:
        """
        Lookup campaign by lightning address
        
        Args:
            lightning_address: Lightning address (e.g., user@domain.com)
            
        Returns:
            CampaignInfo or None if not found
        """
        if not lightning_address:
            return None
        
        # Case-insensitive lookup
        ln_key = lightning_address.lower()
        campaign = self.campaigns.get(ln_key)
        
        if campaign:
            logger.debug(f"Found campaign for {lightning_address}: {campaign.title}")
        else:
            logger.debug(f"No campaign found for {lightning_address}")
        
        return campaign
    
    def should_refresh(self) -> bool:
        """
        Check if campaigns should be refreshed
        
        Returns:
            bool: True if refresh interval has elapsed
        """
        return (time.time() - self.last_refresh) > self.refresh_interval
    
    def get_all_campaigns(self) -> Dict[str, CampaignInfo]:
        """
        Get all cached campaigns
        
        Returns:
            dict: Map of lightning_address -> CampaignInfo
        """
        return self.campaigns.copy()
    
    def get_campaign_count(self) -> int:
        """Get the number of cached campaigns"""
        return len(self.campaigns)
