import json
from decimal import Decimal
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from .models import Account, Trade, Asset, Notification, SiteSettings, UserBrokerAccount
from .deriv_service import DerivService
from .ai_engine import ai_engine

# Contract types settled using the last-digit rule vs. the price-direction rule.
DIGIT_CONTRACTS = {'DIGITEVEN', 'DIGITODD', 'DIGITOVER', 'DIGITUNDER', 'DIGITMATCH', 'DIGITDIFF'}


class TradingConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.deriv_service = DerivService()
        await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')

            if action == 'get_account_balance':
                # Site wallet balance (what trades are actually settled against).
                db_data = await self.get_db_account_data()
                if db_data:
                    await self.send(text_data=json.dumps({'type': 'account_info', 'data': db_data}))
                else:
                    await self.send_error("No site account found for this user.")

            elif action == 'get_deriv_demo_balance' or action == 'get_balance':
                # READ-ONLY: shows the connected Deriv account balance for reference.
                deriv_data = await self.fetch_deriv_demo_balance()
                
                # Safely extract balance value whether it's dict or nested
                if isinstance(deriv_data, dict):
                    balance_val = deriv_data.get('balance', deriv_data.get('amount', '0.00'))
                    if isinstance(balance_val, dict):
                        balance_val = balance_val.get('balance', '0.00')
                else:
                    balance_val = str(deriv_data or '0.00')

                await self.send(text_data=json.dumps({
                    'type': 'balance',
                    'balance': str(balance_val),
                    'data': deriv_data
                }))

            elif action == 'predict_even_odd' or action == 'predict':
                symbol = data.get('symbol', 'R_100')
                prediction = await self.generate_ai_prediction(symbol)
                await self.send(text_data=json.dumps({'type': 'ai_prediction', 'result': prediction}))

            elif action == 'run_bot':
                await self.execute_site_trade(data)

        except Exception as e:
            print(f"❌ Error handling consumer receive: {e}")
            await self.send_error("Something went wrong processing that request.")

    # ------------------------------------------------------------------
    # DB helpers (all DB access must go through database_sync_to_async)
    # ------------------------------------------------------------------
    @database_sync_to_async
    def get_db_account_data(self):
        try:
            account = Account.objects.get(user=self.scope["user"])
            return {'balance': str(account.balance), 'currency': 'USD'}
        except Account.DoesNotExist:
            return None

    @database_sync_to_async
    def get_site_settings(self):
        return SiteSettings.load()

    @database_sync_to_async
    def get_account(self):
        account, _ = Account.objects.get_or_create(user=self.scope["user"])
        return account

    @database_sync_to_async
    def debit_balance(self, stake):
        account, _ = Account.objects.get_or_create(user=self.scope["user"])
        account.balance = Decimal(str(account.balance)) - Decimal(str(stake))
        account.save()
        return account.balance

    @database_sync_to_async
    def open_trade(self, user, symbol, contract_type, stake, entry_price, target_digit=None):
        asset, _ = Asset.objects.get_or_create(
            symbol=symbol,
            defaults={'name': symbol, 'asset_type': 'synthetic', 'price': Decimal(str(entry_price))}
        )
        try:
            parsed_target_digit = int(target_digit) if target_digit is not None else None
        except (TypeError, ValueError):
            parsed_target_digit = None

        return Trade.objects.create(
            user=user,
            asset=asset,
            direction=contract_type,
            stake=Decimal(str(stake)),
            entry_price=Decimal(str(entry_price)),
            target_digit=parsed_target_digit,
            status='OPEN',
        )

    @database_sync_to_async
    def refund_trade(self, trade, stake):
        account, _ = Account.objects.get_or_create(user=trade.user)
        account.balance = Decimal(str(account.balance)) + Decimal(str(stake))
        account.save()
        trade.status = 'CANCELLED'
        trade.save()
        return account.balance

    @database_sync_to_async
    def settle_trade(self, trade, status, payout, settlement_price):
        trade.status = status
        trade.exit_price = Decimal(str(settlement_price))
        trade.payout = payout
        trade.save()

        account, _ = Account.objects.get_or_create(user=trade.user)
        if status == 'WON' and payout > 0:
            account.balance = Decimal(str(account.balance)) + Decimal(str(payout))
            account.save()

        Notification.objects.create(
            user=trade.user,
            title="Trade Closed",
            message=f"Your {trade.asset.symbol} {trade.direction} trade was {status.lower()}."
                     + (f" Payout: ${payout}" if status == 'WON' else "")
        )
        return account.balance

    @database_sync_to_async
    def get_deriv_token(self):
        user = self.scope.get("user")
        if user and not isinstance(user, AnonymousUser) and user.is_authenticated:
            account = UserBrokerAccount.objects.filter(user=user, broker='DERIV', is_active=True).first()
            if account and account.api_token:
                return account.api_token, account.account_number
        
        # Fallback to global settings if no database broker account is linked
        return getattr(settings, 'DERIV_API_TOKEN', None), None
    # ------------------------------------------------------------------
    # Deriv (read-only) helpers
    # ------------------------------------------------------------------
    async def fetch_deriv_demo_balance(self):
        """READ-ONLY balance lookup. Never places or funds a trade."""
        token, account_number = await self.get_deriv_token()
        if not token:
            return {'connected': False, 'message': 'No Deriv account connected.', 'balance': '0.00'}
        
        info = await self.deriv_service.get_account_info(token=token, account_number=account_number or "")
        
        if isinstance(info, dict):
            balance_val = info.get('balance', info.get('amount', '0.00'))
            if isinstance(balance_val, dict):
                balance_val = balance_val.get('balance', '0.00')
            info['balance'] = str(balance_val)
            info['connected'] = True
            return info
            
        return {'connected': True, 'balance': str(info or '0.00'), 'amount': str(info or '0.00')}

    async def generate_ai_prediction(self, symbol):
        ticks = await self.deriv_service.get_recent_ticks(symbol=symbol, count=50)
        result = ai_engine.predict_all_contracts(symbol, ticks)
        if 'error' in result:
            return result

        top = result['top_signal']
        return {
            "symbol": symbol,
            "predicted_contract": top['contract_type'],
            "confidence": top['confidence'],
            "raw_confidence": top['raw_confidence'],
            "last_price": str(result['last_price']),
            "last_digit": result['last_digit'],
            "barrier": top['barrier'],
        }

    # ------------------------------------------------------------------
    # Site trading (settled against the internal Account balance, judged
    # fairly using real, read-only Deriv tick data)
    # ------------------------------------------------------------------
    async def send_error(self, message):
        await self.send(text_data=json.dumps({'type': 'error', 'message': message}))

    @staticmethod
    def evaluate_outcome(contract_type, entry_price, entry_digit, settlement_price, settlement_digit, barrier=None, target_digit=None):
        contract_type = (contract_type or '').upper()

        if contract_type == 'CALL':
            return settlement_price > entry_price
        if contract_type == 'PUT':
            return settlement_price < entry_price
        if contract_type == 'DIGITEVEN':
            return settlement_digit % 2 == 0
        if contract_type == 'DIGITODD':
            return settlement_digit % 2 != 0
        if contract_type == 'DIGITOVER':
            b = int(barrier) if barrier is not None else 4
            return settlement_digit > b
        if contract_type == 'DIGITUNDER':
            b = int(barrier) if barrier is not None else 5
            return settlement_digit < b
        if contract_type == 'DIGITMATCH':
            t = int(target_digit) if target_digit is not None else settlement_digit
            return settlement_digit == t
        if contract_type == 'DIGITDIFF':
            t = int(target_digit) if target_digit is not None else -1
            return settlement_digit != t

        # Unknown contract type: default to the rise/fall rule.
        return settlement_price > entry_price

    async def execute_site_trade(self, data):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.send_error("You must be logged in to trade.")
            return

        settings_obj = await self.get_site_settings()
        if not settings_obj.trading_enabled:
            await self.send_error("Trading is currently paused by the site admin.")
            return

        symbol = data.get('symbol', 'R_100')
        contract_type = (data.get('contract_type') or 'DIGITEVEN').upper()
        barrier = data.get('barrier')
        target_digit = data.get('target_digit')
        duration = data.get('duration', 1)
        try:
            duration = max(1, int(duration))
        except (TypeError, ValueError):
            duration = 1

        requested_amount = data.get('amount')
        try:
            stake = Decimal(str(requested_amount)) if requested_amount not in (None, '') else settings_obj.default_trade_amount
        except Exception:
            stake = settings_obj.default_trade_amount

        if stake < settings_obj.min_trade_amount or stake > settings_obj.max_trade_amount:
            await self.send_error(
                f"Stake must be between {settings_obj.min_trade_amount} and {settings_obj.max_trade_amount} USD."
            )
            return

        account = await self.get_account()
        if account is None or Decimal(str(account.balance)) < stake:
            await self.send_error("Insufficient site balance for this trade.")
            return

        # 1. Get a real entry price from the live (read-only) Deriv feed.
        entry_ticks = await self.deriv_service.get_settlement_ticks(symbol=symbol, count=1, timeout=10)
        if not entry_ticks:
            await self.send_error("Could not reach the live price feed. Please try again.")
            return
        entry_price = entry_ticks[0]
        entry_digit = ai_engine.extract_last_digit(entry_price)

        # 2. Open the trade and debit the stake from the site balance.
        trade = await self.open_trade(user, symbol, contract_type, stake, entry_price, target_digit)
        new_balance = await self.debit_balance(stake)

        await self.send(text_data=json.dumps({
            'type': 'trade_opened',
            'trade_id': trade.id,
            'symbol': symbol,
            'contract_type': contract_type,
            'stake': str(stake),
            'entry_price': entry_price,
            'balance': str(new_balance),
        }))

        # 3. Settle fairly using the next real tick(s) from Deriv's feed.
        settlement_ticks = await self.deriv_service.get_settlement_ticks(symbol=symbol, count=duration, timeout=20)

        if not settlement_ticks:
            refunded_balance = await self.refund_trade(trade, stake)
            await self.send(text_data=json.dumps({
                'type': 'trade_result',
                'trade_id': trade.id,
                'status': 'CANCELLED',
                'message': 'Live price feed was unavailable — stake refunded.',
                'balance': str(refunded_balance),
            }))
            return

        settlement_price = settlement_ticks[-1]
        settlement_digit = ai_engine.extract_last_digit(settlement_price)

        won = self.evaluate_outcome(
            contract_type, entry_price, entry_digit, settlement_price, settlement_digit, barrier, target_digit
        )

        payout = Decimal('0.00')
        if won:
            payout = (stake * (Decimal('1') + Decimal(str(settings_obj.payout_percentage)) / Decimal('100'))).quantize(Decimal('0.01'))

        final_balance = await self.settle_trade(trade, 'WON' if won else 'LOST', payout, settlement_price)

        await self.send(text_data=json.dumps({
            'type': 'trade_result',
            'trade_id': trade.id,
            'status': 'WON' if won else 'LOST',
            'entry_price': entry_price,
            'settlement_price': settlement_price,
            'payout': str(payout),
            'balance': str(final_balance),
        }))