import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .deriv_service import DerivService
from .ai_engine import ai_engine  # Imports multi-contract AI engine
from .models import UserBrokerAccount, Trade, Asset


class TradingConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.deriv_service = DerivService()
        self.stream_task = None
        self.active_symbol = "R_100"  # Default Volatility 100 Index

    async def connect(self):
        await self.accept()
        print("⚡ [WebSocket] Client connected to Deriv Volatility Engine")
        self.stream_task = asyncio.create_task(self.start_live_stream())

    async def disconnect(self, close_code):
        if self.stream_task:
            self.stream_task.cancel()

    @database_sync_to_async
    def get_user_account_details(self):
        user = self.scope.get("user")
        if user and user.is_authenticated:
            broker_acc = UserBrokerAccount.objects.filter(user=user, broker='DERIV', is_active=True).first()
            if broker_acc:
                return broker_acc.api_token, broker_acc.account_number
        return None, "1089"

    @database_sync_to_async
    def save_trade_record(self, symbol, contract_type, stake, result):
        user = self.scope.get("user")
        if user and user.is_authenticated and result.get("success"):
            asset, _ = Asset.objects.get_or_create(symbol=symbol, defaults={"name": symbol})
            Trade.objects.create(
                user=user,
                asset=asset,
                direction=contract_type,
                stake=stake,
                entry_price=result.get("buy_price", 0.0),
                status='OPEN'
            )

    async def start_live_stream(self):
        try:
            while True:
                user_token, account_number = await self.get_user_account_details()
                
                # 1. Get live account balance & info
                account_info = await self.deriv_service.get_account_info(
                    token=user_token, 
                    account_number=account_number
                )
                
                # 2. Fetch live tick buffer for active symbol
                recent_ticks = await self.deriv_service.get_recent_ticks(symbol=self.active_symbol)
                
                # 3. Generate Multi-Contract AI Predictions (Rise/Fall, Even/Odd, Over/Under, Matches/Differs)
                prediction = ai_engine.predict_all_contracts(self.active_symbol, recent_ticks)

                # 4. Stream real-time metrics back to dashboard
                await self.send(text_data=json.dumps({
                    'type': 'stream_update',
                    'account_data': account_info,
                    'result': prediction
                }))
                await asyncio.sleep(2.5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"❌ Streaming Loop Error: {e}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')
            user_token, account_number = await self.get_user_account_details()

            # Update active stream symbol dynamically if passed
            if data.get('symbol'):
                self.active_symbol = data.get('symbol')

            # -------------------------------------------------------------
            # ACTION: EXECUTE TRADE / RUN BOT
            # -------------------------------------------------------------
            if action in ['execute_trade', 'run_bot']:
                symbol = data.get('symbol', self.active_symbol)
                contract_type = data.get('contract_type', 'DIGITEVEN')
                stake = float(data.get('stake', data.get('amount', 10.0)))
                duration = int(data.get('duration', 1))
                duration_unit = data.get('duration_unit', 't')
                barrier = data.get('barrier', None)  # Needed for Over/Under/Match/Differ

                # Execute trade on Deriv WebSocket/REST API
                trade_result = await self.deriv_service.execute_trade(
                    token=user_token,
                    symbol=symbol,
                    contract_type=contract_type,
                    stake=stake,
                    duration=duration,
                    duration_unit=duration_unit,
                    barrier=barrier
                )

                # Save record to Django DB if successful
                if trade_result.get("success"):
                    await self.save_trade_record(symbol, contract_type, stake, trade_result)

                # Refresh balance
                account_info = await self.deriv_service.get_account_info(
                    token=user_token, 
                    account_number=account_number
                )

                # Respond back to frontend
                await self.send(text_data=json.dumps({
                    'type': 'bot_trade_result',
                    'result': trade_result,
                    'account_data': account_info
                }))

            # -------------------------------------------------------------
            # ACTION: REQUEST AI PREDICTION
            # -------------------------------------------------------------
            elif action in ['predict_all', 'predict_even_odd']:
                symbol = data.get('symbol', self.active_symbol)
                recent_ticks = await self.deriv_service.get_recent_ticks(symbol=symbol)
                prediction = ai_engine.predict_all_contracts(symbol, recent_ticks)

                await self.send(text_data=json.dumps({
                    'type': 'ai_prediction',
                    'result': prediction
                }))

            # -------------------------------------------------------------
            # ACTION: FETCH ACCOUNT BALANCE
            # -------------------------------------------------------------
            elif action == 'get_account_balance':
                account_info = await self.deriv_service.get_account_info(
                    token=user_token, 
                    account_number=account_number
                )
                await self.send(text_data=json.dumps({
                    'type': 'account_info',
                    'data': account_info
                }))

        except Exception as e:
            print(f"❌ WebSocket Receive Error: {e}")