"""
BTCPay Server API Client
Fetches invoice details from BTCPay Server API
"""
import requests
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

class BTCPayClient:
    """Client for BTCPay Server API"""
    
    def __init__(self, server_url: str, api_key: Optional[str] = None, store_id: Optional[str] = None):
        """
        Initialize BTCPay client
        
        Args:
            server_url: BTCPay server URL (e.g., https://btcpay.example.com)
            api_key: BTCPay API key (optional for public endpoints)
            store_id: Store ID (optional, can be extracted from webhooks)
        """
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.store_id = store_id
        self.session = requests.Session()
        
        if api_key:
            self.session.headers['Authorization'] = f'token {api_key}'
    
    def get_invoice(self, store_id: str, invoice_id: str) -> Optional[Dict]:
        """
        Fetch invoice details from BTCPay Server
        
        Args:
            store_id: Store ID
            invoice_id: Invoice ID
            
        Returns:
            dict: Invoice data or None if error
        """
        try:
            url = f"{self.server_url}/api/v1/stores/{store_id}/invoices/{invoice_id}"
            logger.debug(f"[BTCPay] Fetching invoice from: {url}")
            
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                invoice_data = response.json()
                logger.debug(f"[BTCPay] Invoice fetched successfully")
                return invoice_data
            elif response.status_code == 404:
                logger.warning(f"[BTCPay] Invoice not found: {invoice_id}")
                return None
            else:
                logger.error(f"[BTCPay] API error: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("[BTCPay] Request timeout")
            return None
        except Exception as e:
            logger.error(f"[BTCPay] Error fetching invoice: {e}")
            return None
    
    def extract_amount_from_invoice(self, invoice_data: Dict) -> int:
        """
        Extract the paid amount in sats from invoice data
        
        Args:
            invoice_data: Invoice data from BTCPay API
            
        Returns:
            int: Amount in satoshis
        """
        try:
            # BTCPay invoice structure has amount in different fields
            # Try to get the actual paid crypto amount
            
            # Option 1: Check amount field (in fiat usually)
            # Option 2: Check checkout->cryptoCode specific amount
            # Option 3: Check payment method data
            
            # For Lightning/Bitcoin payments, look for the crypto amount
            if 'amount' in invoice_data:
                # This is usually the fiat amount, but might be crypto if that's the denomination
                amount = float(invoice_data['amount'])
                currency = invoice_data.get('currency', 'USD')
                
                # If currency is BTC/SATS, use directly
                if currency.upper() in ['BTC', 'SATS', 'SAT']:
                    if currency.upper() == 'BTC':
                        return round(amount * 100000000)  # BTC to sats
                    else:
                        return round(amount)  # Already in sats, round to nearest
            
            # Try to get from checkout information
            if 'checkout' in invoice_data:
                checkout = invoice_data['checkout']
                
                # Look for BTC/Lightning amount
                if 'cryptoCode' in checkout and 'cryptoAmount' in checkout:
                    crypto_code = checkout['cryptoCode']
                    crypto_amount = float(checkout['cryptoAmount'])
                    
                    if crypto_code.upper() in ['BTC', 'BTCLN']:
                        return round(crypto_amount * 100000000)  # BTC to sats
            
            # Try to get from metadata
            if 'metadata' in invoice_data:
                metadata = invoice_data['metadata']
                if 'cryptoAmount' in metadata:
                    return round(float(metadata['cryptoAmount']) * 100000000)
            
            logger.warning(f"[BTCPay] Could not extract crypto amount from invoice data")
            logger.debug(f"[BTCPay] Invoice data keys: {list(invoice_data.keys())}")
            return 0
            
        except Exception as e:
            logger.error(f"[BTCPay] Error extracting amount: {e}")
            return 0
    
    def get_invoice_payment_methods(self, store_id: str, invoice_id: str) -> Optional[List[Dict]]:
        """
        Get payment methods for an invoice
        
        Args:
            store_id: BTCPay Store ID
            invoice_id: Invoice ID
            
        Returns:
            list: Payment methods data or None if error
        """
        try:
            url = f"{self.server_url}/api/v1/stores/{store_id}/invoices/{invoice_id}/payment-methods"
            logger.debug(f"[BTCPay] Fetching payment methods from: {url}")
            
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                payment_methods = response.json()
                logger.debug(f"[BTCPay] Payment methods fetched successfully")
                return payment_methods
            else:
                logger.warning(f"[BTCPay] Could not fetch payment methods: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"[BTCPay] Error fetching payment methods: {e}")
            return None
    
    def extract_lightning_address_from_invoice(self, invoice_data: Dict, payment_methods: Optional[List[Dict]] = None) -> Optional[str]:
        """
        Extract the destination lightning address from invoice data and payment methods
        
        Args:
            invoice_data: Invoice data from BTCPay API
            payment_methods: Optional payment methods data from BTCPay API
            
        Returns:
            str: Lightning address or None if not found
        """
        try:
            # Option 1: Check payment methods additionalData (most reliable for LNURL)
            if payment_methods:
                for pm in payment_methods:
                    if pm.get('paymentMethodId') in ['BTC-LNURL', 'BTC-LightningLike']:
                        additional_data = pm.get('additionalData', {})
                        consumed_address = additional_data.get('consumedLightningAddress')
                        if consumed_address:
                            logger.debug(f"[BTCPay] Found lightning address in payment methods: {consumed_address}")
                            return consumed_address
            
            # Option 2: Check metadata for lightning address
            if 'metadata' in invoice_data:
                metadata = invoice_data['metadata']
                
                # Check various possible field names
                for field_name in ['lightningAddress', 'lightning_address', 'lnaddress', 'ln_address']:
                    if field_name in metadata:
                        ln_address = metadata[field_name]
                        logger.debug(f"[BTCPay] Found lightning address in metadata.{field_name}: {ln_address}")
                        return ln_address
            
            # Option 3: Check checkout information
            if 'checkout' in invoice_data:
                checkout = invoice_data['checkout']
                
                for field_name in ['destination', 'lightningAddress', 'paymentDestination']:
                    if field_name in checkout:
                        ln_address = checkout[field_name]
                        logger.debug(f"[BTCPay] Found lightning address in checkout.{field_name}: {ln_address}")
                        return ln_address
            
            # Option 4: Check top-level fields
            for field_name in ['lightningAddress', 'destination', 'recipientAddress']:
                if field_name in invoice_data:
                    ln_address = invoice_data[field_name]
                    logger.debug(f"[BTCPay] Found lightning address in {field_name}: {ln_address}")
                    return ln_address
            
            logger.debug("[BTCPay] No lightning address found in invoice data or payment methods")
            return None
            
        except Exception as e:
            logger.error(f"[BTCPay] Error extracting lightning address: {e}")
            return None

