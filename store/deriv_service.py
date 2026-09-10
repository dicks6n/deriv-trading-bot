"""
Deriv Service — Uses OTP-based WebSocket authentication.
The new Deriv API requires fetching an OTP via REST before opening
the WebSocket connection. Direct token-based WebSocket connections
are rejected with HTTP 401.
"""
import json
import logging
import ssl
import asyncio
import random
import time
import websockets
import requests
import pandas as pd
from django.conf import settings

logger = logging.getLogger(__name__)

# SSL context for secure WebSocket connections
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Public WebSocket (no auth needed) — used for market data (ticks)
PUBLIC_WS_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

# REST base for OTP + authenticated endpoints
REST_BASE_URL = "https://api.derivws.com"

SYMBOL_MAP = {
    "Gold / USD (XAU)": "frxXAUUSD",
    "Volatility 100 Index": "R_100",
    "Volatility 75 Index": "R_75",
    "Volatility 50 Index": "R_50",
    "Volatility 25 Index": "R_25",
    "Volatility 10 Index": "R_10",
    "EUR/USD": "frxEURUSD",
    "GBP/USD": "frxGBPUSD",
    "USD/JPY": "frxUSDJPY",
    "BTC/USD": "cryBTCUSD",
}

# Base prices for fallback tick generation
BASE_PRICES = {
    'R_10': 1000.00,
    'R_25': 2500.00,
    'R_50': 5000.00,
    'R_75': 7500.00,
    'R_100': 10000.00,
    '1HZ10V': 1000.00,
    '1HZ25V': 2500.00,
    '1HZ50V': 5000.00,
    '1HZ75V': 7500.00,
    '1HZ100V': 10000.00,
    'frxXAUUSD': 4454.08,
    'frxXTIUSD': 83.44,
    'frxEURUSD': 1.1583,
    'frxGBPUSD': 1.2940,
    'frxUSDJPY': 146.15,
    'frxEURGBP': 0.8415,
    'frxEURJPY': 159.20,
    'frxGBPJPY': 189.10,
    'cryBTCUSD': 78912.33,
    'cryETHUSD': 3456.78,
}


class DerivService:
    def __init__(self):
        self.app_id = getattr(settings, 'DERIV_APP_ID', '')
        self.api_token = getattr(settings, 'DERIV_API_TOKEN', '')
        self._use_fallback = False
        self._last_prices = {}

    def resolve_symbol(self, raw_symbol):
        return SYMBOL_MAP.get(raw_symbol, raw_symbol)

    # ==========================================
    # OTP FLOW — Get authenticated WebSocket URL
    # ==========================================

    def _get_authenticated_ws_url(self, token, account_number):
        """
        Calls Deriv's REST endpoint to obtain a one-time-password
        and returns the ready-to-use authenticated WebSocket URL.

        Returns:
            str — the authenticated wss:// URL, or None on failure.
        """
        endpoint = f"{REST_BASE_URL}/trading/v1/options/accounts/{account_number}/otp"
        headers = {
            "Deriv-App-ID": self.app_id,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(endpoint, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            ws_url = data.get('data', {}).get('url')
            if not ws_url:
                logger.warning(f"OTP response missing 'url' field: {data}")
                return None
            return ws_url
        except requests.HTTPError as e:
            logger.warning(f"OTP request HTTP error: {e} — {getattr(e.response, 'text', '')[:200]}")
            return None
        except Exception as e:
            logger.warning(f"OTP request failed: {e}")
            return None

    # ==========================================
    # ACCOUNT INFO (via OTP-authenticated WebSocket)
    # ==========================================

    async def get_account_info(self, token=None, account_number=""):
        """
        Fetches balance and account details via OTP-authenticated WebSocket.
        Falls back to demo info if anything fails.
        """
        active_token = token or self.api_token

        if not active_token or not account_number:
            return self._demo_account_info(account_number)

        # 1. Get authenticated WebSocket URL via OTP
        ws_url = await asyncio.to_thread(
            self._get_authenticated_ws_url, active_token, account_number
        )
        if not ws_url:
            logger.warning("Could not obtain authenticated WebSocket URL, using demo fallback")
            return self._demo_account_info(account_number)

        # 2. Connect and fetch balance
        try:
            async with websockets.connect(
                ws_url,
                ssl=ssl_context,
                open_timeout=8,
                ping_interval=20,
                ping_timeout=10,
            ) as ws:
                # Request balance subscription
                await ws.send(json.dumps({"balance": 1, "subscribe": 1}))

                balance = None
                currency = "USD"
                loginid = account_number
                is_virtual = False

                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < 8:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        msg = json.loads(raw)

                        if msg.get('msg_type') == 'balance' and 'balance' in msg:
                            balance = float(msg['balance'].get('balance', 0))
                            currency = msg['balance'].get('currency', 'USD')
                            loginid = msg['balance'].get('loginid', account_number)
                            break

                        if msg.get('msg_type') == 'error':
                            logger.warning(f"Deriv error: {msg.get('error', {}).get('message')}")
                            break
                    except asyncio.TimeoutError:
                        break

                if balance is None:
                    logger.warning("No balance returned from Deriv WebSocket")
                    return self._demo_account_info(account_number)

                return {
                    "balance": f"{balance:,.2f}",
                    "raw_balance": balance,
                    "currency": currency,
                    "is_demo": is_virtual,
                    "loginid": str(loginid),
                    "server": "Deriv-Server",
                    "connected": True,
                }

        except Exception as e:
            logger.warning(f"Deriv Account Info Error: {e}")
            return self._demo_account_info(account_number)

    def _demo_account_info(self, account_number=""):
        """Return demo account info when Deriv is unavailable"""
        return {
            "balance": "10,000.00",
            "raw_balance": 10000.00,
            "currency": "USD",
            "is_demo": True,
            "loginid": f"MT5:{account_number or 'DEMO'}",
            "server": "Deriv-Demo",
            "connected": False,
        }

    # ==========================================
    # TICKS — Public WebSocket, no auth needed
    # ==========================================

    async def get_recent_ticks(self, symbol="frxXAUUSD", count=50):
        """Get recent historical ticks — uses PUBLIC WebSocket, no auth."""
        deriv_symbol = self.resolve_symbol(symbol)

        if self._use_fallback:
            return self._fallback_ticks(deriv_symbol, count)

        try:
            async with websockets.connect(
                PUBLIC_WS_URL,
                ssl=ssl_context,
                open_timeout=5,
                ping_interval=20,
                ping_timeout=10,
            ) as ws:
                req = {
                    "ticks_history": deriv_symbol,
                    "adjust_start_time": 1,
                    "count": count,
                    "end": "latest",
                    "style": "ticks",
                }
                await ws.send(json.dumps(req))
                res = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))

                if "error" in res:
                    logger.warning(f"Deriv ticks error for {deriv_symbol}: {res['error']}")
                    self._use_fallback = True
                    return self._fallback_ticks(deriv_symbol, count)

                if "history" in res and "prices" in res["history"]:
                    prices = [float(p) for p in res["history"]["prices"]]
                    if prices:
                        self._last_prices[deriv_symbol] = prices[-1]
                    return prices

        except Exception as e:
            logger.warning(f"Fallback tick generator for {deriv_symbol}: {e}")
            self._use_fallback = True

        return self._fallback_ticks(deriv_symbol, count)

    async def get_settlement_ticks(self, symbol, count=1, timeout=10):
        """Get settlement ticks — uses PUBLIC WebSocket, no auth."""
        deriv_symbol = self.resolve_symbol(symbol)

        if self._use_fallback:
            return self._fallback_ticks(deriv_symbol, count)

        try:
            async with websockets.connect(
                PUBLIC_WS_URL,
                ssl=ssl_context,
                open_timeout=5,
                ping_interval=20,
                ping_timeout=10,
            ) as ws:
                await ws.send(json.dumps({"ticks": deriv_symbol, "subscribe": 1}))

                ticks = []
                start_time = asyncio.get_event_loop().time()

                while len(ticks) < count:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > timeout:
                        break
                    try:
                        remaining = max(0.5, timeout - elapsed)
                        response = await asyncio.wait_for(ws.recv(), timeout=remaining)
                        data = json.loads(response)

                        if "error" in data:
                            logger.warning(f"Deriv settlement error: {data['error']}")
                            self._use_fallback = True
                            return self._fallback_ticks(deriv_symbol, count)

                        if "tick" in data and "quote" in data["tick"]:
                            quote = float(data["tick"]["quote"])
                            ticks.append(quote)
                            self._last_prices[deriv_symbol] = quote
                    except asyncio.TimeoutError:
                        break

                try:
                    await ws.send(json.dumps({"forget_all": "ticks"}))
                except Exception:
                    pass

                if ticks:
                    return ticks

        except Exception as e:
            logger.warning(f"Error getting settlement ticks for {deriv_symbol}: {e}")
            self._use_fallback = True

        return self._fallback_ticks(deriv_symbol, count)

    # ==========================================
    # FALLBACK
    # ==========================================

    def _fallback_ticks(self, symbol, count):
        """Generate realistic fallback ticks when WebSocket is unavailable."""
        base = self._last_prices.get(symbol) or BASE_PRICES.get(symbol, 1000.00)

        if "XAU" in symbol:
            volatility = 0.5
        elif "BTC" in symbol or "ETH" in symbol:
            volatility = 50.0
        elif "R_100" in symbol:
            volatility = 15.0
        elif "R_75" in symbol:
            volatility = 10.0
        elif "JPY" in symbol:
            volatility = 0.05
        else:
            volatility = base * 0.0005

        ticks = []
        current = base
        for _ in range(count):
            change = (random.random() - 0.5) * 2 * volatility
            current += change
            if base > 100:
                ticks.append(round(current, 2))
            elif base > 1:
                ticks.append(round(current, 3))
            else:
                ticks.append(round(current, 5))

        if ticks:
            self._last_prices[symbol] = ticks[-1]
        return ticks

    # ==========================================
    # OHLC AGGREGATION
    # ==========================================

    def aggregate_ticks_to_ohlc(self, ticks_response, interval_minutes=1):
        """Aggregates raw API tick data into OHLCV dictionaries."""
        if not ticks_response:
            return None

        if isinstance(ticks_response, list):
            prices = ticks_response
            now = int(time.time())
            epochs = [now - (len(prices) - i) for i in range(len(prices))]
        elif 'ticks' in ticks_response:
            ticks = ticks_response['ticks']
            prices = [float(t['quote']) for t in ticks]
            epochs = [t['epoch'] for t in ticks]
        else:
            return None

        if not prices:
            return None

        index = pd.to_datetime(epochs, unit='s')
        series = pd.Series(data=prices, index=index)
        ohlc_resampled = series.resample(f'{interval_minutes}min').ohlc()
        ohlc_resampled.columns = [col.lower() for col in ohlc_resampled.columns]
        ohlc_resampled.reset_index(inplace=True)
        ohlc_resampled.dropna(inplace=True)
        return ohlc_resampled.to_dict(orient='records')

    # ==========================================
    # UTILITY
    # ==========================================

    def reset_fallback(self):
        """Reset the fallback flag to try live connection again."""
        self._use_fallback = False
        logger.info("Fallback flag reset - will try live connection")