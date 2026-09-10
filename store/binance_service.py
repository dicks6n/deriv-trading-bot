"""
Binance Spot balance service.
Read-only — only fetches balance, never places orders.
"""
import hmac
import hashlib
import time
import logging
import requests
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)


class BinanceService:
    BASE_URL = 'https://api.binance.com'

    def __init__(self, api_key=None, api_secret=None):
        self.api_key = api_key
        self.api_secret = api_secret

    def _sign(self, query_string: str) -> str:
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _signed_get(self, endpoint: str, params: dict = None) -> dict:
        """Make a signed GET request to Binance API"""
        params = params or {}
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 5000

        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        signature = self._sign(query_string)
        url = f"{self.BASE_URL}{endpoint}?{query_string}&signature={signature}"

        headers = {'X-MBX-APIKEY': self.api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_account_info(self) -> dict:
        """Fetch account info with balances"""
        return self._signed_get('/api/v3/account')

    def get_stablecoin_balance(self) -> dict:
        """
        Returns total stablecoin balance (USDT + USDC + BUSD + FDUSD).
        This is what we display as the Binance spot balance.
        """
        try:
            data = self.get_account_info()
        except requests.HTTPError as e:
            error_msg = "Invalid API key or permissions"
            try:
                error_body = e.response.json()
                error_msg = error_body.get('msg', error_msg)
            except Exception:
                pass
            return {'success': False, 'error': error_msg}
        except Exception as e:
            return {'success': False, 'error': str(e)}

        stablecoins = ['USDT', 'USDC', 'BUSD', 'FDUSD']
        total = Decimal('0.00')
        breakdown = {}

        for bal in data.get('balances', []):
            asset = bal.get('asset')
            if asset in stablecoins:
                free = Decimal(str(bal.get('free', '0')))
                locked = Decimal(str(bal.get('locked', '0')))
                amount = free + locked
                if amount > 0:
                    total += amount
                    breakdown[asset] = float(amount)

        return {
            'success': True,
            'balance': float(total),
            'currency': 'USDT',
            'breakdown': breakdown,
            'raw': {'accountType': data.get('accountType', 'SPOT')},
        }

    def validate_credentials(self) -> tuple:
        """Returns (is_valid, error_message)"""
        try:
            self.get_account_info()
            return True, None
        except requests.HTTPError as e:
            try:
                body = e.response.json()
                return False, body.get('msg', 'Invalid credentials')
            except Exception:
                return False, f"HTTP {e.response.status_code}"
        except Exception as e:
            return False, str(e)