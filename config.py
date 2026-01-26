"""
Configuration management for BTCPay to Nostr bridge service
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Service configuration loaded from environment variables"""
    
    # Nostr Configuration
    NOSTR_PRIVATE_KEY = os.getenv('NOSTR_PRIVATE_KEY', '')
    NOSTR_RELAY_URL = os.getenv('NOSTR_RELAY_URL', '')
    
    # Campaign Configuration (Dynamic - loaded from relay)
    CAMPAIGN_REFRESH_INTERVAL = int(os.getenv('CAMPAIGN_REFRESH_INTERVAL', '300'))  # 5 minutes
    
    # BTCPay Configuration
    BTCPAY_WEBHOOK_SECRET = os.getenv('BTCPAY_WEBHOOK_SECRET', '')
    BTCPAY_SERVER_URL = os.getenv('BTCPAY_SERVER_URL', '')
    BTCPAY_API_KEY = os.getenv('BTCPAY_API_KEY', '')  # Optional - for fetching invoice details
    
    # Service Configuration
    WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8765'))
    WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '0.0.0.0')  # Listen on all interfaces (for Docker access)
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """Validate that all required configuration is present"""
        errors = []
        
        if not cls.NOSTR_PRIVATE_KEY:
            errors.append("NOSTR_PRIVATE_KEY is required")
        
        if not cls.NOSTR_RELAY_URL:
            errors.append("NOSTR_RELAY_URL is required")
        
        if not cls.BTCPAY_WEBHOOK_SECRET:
            errors.append("BTCPAY_WEBHOOK_SECRET is required")
        
        if not cls.BTCPAY_SERVER_URL:
            errors.append("BTCPAY_SERVER_URL is required")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        return True
    
    @classmethod
    def print_config(cls):
        """Print non-sensitive configuration for debugging"""
        print("=" * 80)
        print("BTCPay to Nostr Bridge - Configuration")
        print("=" * 80)
        print(f"Nostr Relay: {cls.NOSTR_RELAY_URL}")
        print(f"Campaign Mode: DYNAMIC (loaded from relay)")
        print(f"Campaign Refresh: {cls.CAMPAIGN_REFRESH_INTERVAL}s")
        print(f"Private Key: {'SET' if cls.NOSTR_PRIVATE_KEY else 'NOT SET'}")
        print(f"Webhook Secret: {'SET' if cls.BTCPAY_WEBHOOK_SECRET else 'NOT SET'}")
        print(f"Webhook Port: {cls.WEBHOOK_PORT}")
        print(f"Webhook Host: {cls.WEBHOOK_HOST}")
        print(f"Debug Mode: {cls.DEBUG}")
        print("=" * 80)

