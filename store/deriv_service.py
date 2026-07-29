import json
import logging
import ssl
import asyncio
import random
import websockets
from django.conf import settings
from .ai_model import EvenOddAIPredictor
import os

APP_ID = getattr(settings, 'DERIV_APP_ID', '1089')
DERIV_WS_URL = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"

logger = logging.getLogger(__name__)

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

SYMBOL_MAP = {
    "Gold / USD (XAU)": "frxXAUUSD",
    "Volatility 100 Index": "R_100",
    "Volatility 75 Index": "R_75",
    "Volatility 50 Index": "R_50",
    "EUR/USD": "frxEURUSD",
    "GBP/USD": "frxGBPUSD",
}


class DerivService:
    def __init__(self):
        self.app_id = getattr(settings, 'DERIV_APP_ID', '1089')
        self.api_token = getattr(settings, 'DERIV_API_TOKEN', '')
        self.ws_url = f"wss://ws.derivws.com/websockets/v3?app_id={self.app_id}"
        self.ai_engine = EvenOddAIPredictor()

    def resolve_symbol(self, raw_symbol):
        return SYMBOL_MAP.get(raw_symbol, raw_symbol)

    async def get_account_info(self, token=None, account_number="32337661"):
        active_token = token or self.api_token

        if not active_token:
            return {
                "balance": "10,000.00",
                "currency": "USD",
                "is_demo": True,
                "loginid": f"MT5:{account_number}",
                "server": "Deriv-Demo"
            }

        try:
            async with websockets.connect(self.ws_url, ssl=ssl_context, timeout=4) as ws:
                # 1. Authorize API Token
                await ws.send(json.dumps({"authorize": active_token}))
                auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))

                if "error" in auth_res:
                    return {
                        "balance": "10,000.00",
                        "currency": "USD",
                        "is_demo": True,
                        "loginid": f"MT5:{account_number}",
                        "server": "Deriv-Demo"
                    }

                # 2. Fetch MT5 login list for MT5 Demo Account balance
                await ws.send(json.dumps({"mt5_login_list": 1}))
                mt5_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                mt5_accounts = mt5_res.get("mt5_login_list", [])

                if mt5_accounts:
                    target_mt5 = next(
                        (acc for acc in mt5_accounts if str(acc.get("login")) == str(account_number)),
                        mt5_accounts[0]
                    )
                    mt5_balance = target_mt5.get("balance", 10000.00)
                    mt5_login = target_mt5.get("login", account_number)
                    mt5_currency = target_mt5.get("currency", "USD")

                    return {
                        "balance": f"{float(mt5_balance):,.2f}",
                        "raw_balance": float(mt5_balance),
                        "currency": mt5_currency,
                        "is_demo": True,
                        "loginid": f"MT5:{mt5_login}",
                        "server": "Deriv-Demo"
                    }

                # Standard authorization fallback
                auth_data = auth_res.get("authorize", {})
                balance = auth_data.get("balance", 10000.00)
                loginid = auth_data.get("loginid", account_number)
                is_demo = auth_data.get("is_virtual") == 1 or str(loginid).startswith("VRTC")

                return {
                    "balance": f"{float(balance):,.2f}",
                    "raw_balance": float(balance),
                    "currency": auth_data.get("currency", "USD"),
                    "is_demo": is_demo,
                    "loginid": str(loginid),
                    "server": "Deriv-Server"
                }

        except Exception as e:
            logger.warning(f"Deriv MT5 WebSocket Error: {e}")
            return {
                "balance": "10,000.00",
                "currency": "USD",
                "is_demo": True,
                "loginid": f"MT5:{account_number}",
                "server": "Deriv-Demo"
            }

    async def get_recent_ticks(self, symbol="frxXAUUSD", count=50):
        deriv_symbol = self.resolve_symbol(symbol)
        try:
            async with websockets.connect(self.ws_url, ssl=ssl_context, timeout=3) as ws:
                req = {
                    "ticks_history": deriv_symbol,
                    "adjust_start_time": 1,
                    "count": count,
                    "end": "latest",
                    "style": "ticks"
                }
                await ws.send(json.dumps(req))
                res = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))

                if "history" in res and "prices" in res["history"]:
                    return res["history"]["prices"]
        except Exception as e:
            logger.warning(f"Fallback tick generator for {deriv_symbol}: {e}")

        base_price = 2742.50 if "XAU" in deriv_symbol else 1245.80
        return [round(base_price + random.uniform(-1.5, 1.5), 2) for _ in range(30)]

    async def run_ai_trade_decision(self, symbol="Gold / USD (XAU)"):
        deriv_symbol = self.resolve_symbol(symbol)
        ticks = await self.get_recent_ticks(symbol=deriv_symbol, count=50)

        self.ai_engine.train(ticks)
        predicted_contract, confidence = self.ai_engine.predict_next(ticks)

        last_price = ticks[-1]
        last_digit = self.ai_engine.extract_last_digit(last_price)

        return {
            "display_symbol": symbol,
            "symbol": deriv_symbol,
            "predicted_contract": predicted_contract,
            "signal": "BUY (EVEN)" if predicted_contract == "DIGITEVEN" else "SELL (ODD)",
            "confidence": f"{confidence}%",
            "raw_confidence": confidence,
            "last_price": f"{last_price:,.2f}",
            "last_digit": last_digit,
            "status": "Active"
        }

    async def execute_trade(self, token, symbol="R_100", contract_type="DIGITEVEN", stake=10.0, duration=1, duration_unit="t"):
        """Sends a 2-step Proposal and Buy command to Deriv via WebSocket."""
        active_token = token or self.api_token
        deriv_symbol = self.resolve_symbol(symbol)

        if not active_token or active_token == 'demo_token_xyz':
            return {
                "success": False,
                "error": "Please connect your real Deriv API Token using the 'Connect Deriv' button to execute live trades."
            }

        try:
            async with websockets.connect(self.ws_url, ssl=ssl_context, timeout=5) as ws:
                # 1. Authorize connection
                await ws.send(json.dumps({"authorize": active_token}))
                auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))

                if "error" in auth_res:
                    return {"success": False, "error": auth_res["error"].get("message", "Authorization failed")}

                # 2. Request Price Proposal for Contract
                proposal_req = {
                    "proposal": 1,
                    "amount": float(stake),
                    "basis": "stake",
                    "contract_type": contract_type,  # 'DIGITEVEN' or 'DIGITODD'
                    "currency": "USD",
                    "duration": int(duration),
                    "duration_unit": duration_unit,  # 't' for ticks
                    "symbol": deriv_symbol
                }

                await ws.send(json.dumps(proposal_req))
                proposal_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))

                if "error" in proposal_res:
                    return {"success": False, "error": proposal_res["error"].get("message", "Proposal error")}

                proposal_id = proposal_res["proposal"]["id"]
                ask_price = proposal_res["proposal"]["ask_price"]

                # 3. Execute Buy Command
                buy_req = {
                    "buy": proposal_id,
                    "price": ask_price
                }

                await ws.send(json.dumps(buy_req))
                buy_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=4))

                if "error" in buy_res:
                    return {"success": False, "error": buy_res["error"].get("message", "Purchase error")}

                contract_info = buy_res.get("buy", {})
                return {
                    "success": True,
                    "contract_id": contract_info.get("contract_id"),
                    "transaction_id": contract_info.get("transaction_id"),
                    "buy_price": contract_info.get("buy_price"),
                    "balance_after": contract_info.get("balance_after"),
                    "message": f"Successfully purchased {contract_type} on {symbol}!"
                }

        except Exception as e:
            logger.error(f"Deriv Trade Execution Error: {e}")
            return {"success": False, "error": str(e)}        