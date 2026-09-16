import json
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subscription_tier = models.CharField(max_length=50, default='free')
    is_active_subscription = models.BooleanField(default=False)
    is_kyc_verified = models.BooleanField(default=False)
    kyc_submitted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.user.username



class UserBot(models.Model):
    """
    Stores persistent state for complex bots (e.g., ComplexVolatilityBot).
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_bots')
    name = models.CharField(max_length=100, help_text="Custom name for bot instance")
    config_json = models.JSONField(default=dict, help_text="Bot strategy parameters")
    state_json = models.JSONField(default=dict, help_text="Current running state of the bot")
    is_running = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.user.username}) - {'Running' if self.is_running else 'Stopped'}"


class Asset(models.Model):
    ASSET_TYPES = [
        ('crypto', 'Crypto'),
        ('forex', 'Forex'),
        ('stock', 'Stock'),
        ('synthetic', 'Synthetic Index')
    ]
    symbol = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPES, default='crypto')
    price = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    change_percent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    digit_precision = models.IntegerField(default=2, help_text="Decimals for digit analysis")

    def __str__(self):
        return f"{self.symbol} ({self.get_asset_type_display()})"

    @property
    def last_digit(self):
        price_str = f"{self.price:.{self.digit_precision}f}".replace(".", "")
        return int(price_str[-1]) if price_str else 0


class PriceTick(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="ticks")
    price = models.DecimalField(max_digits=18, decimal_places=4)
    last_digit = models.IntegerField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def save(self, *args, **kwargs):
        if self.asset and self.price is not None:
            price_str = f"{self.price:.{self.asset.digit_precision}f}".replace(".", "")
            if price_str:
                self.last_digit = int(price_str[-1])
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.asset.symbol} @ {self.price} (Digit: {self.last_digit})"


class AITradingStrategy(models.Model):
    STRATEGY_TYPES = (
        ('EVEN_ODD', 'Even / Odd Probability'),
        ('OVER_UNDER', 'Over / Under Threshold'),
        ('MATCH_DIFF', 'Match / Differ Pattern'),
        ('SENTIMENT_NLP', 'News Sentiment NLP (FinBERT)'),
    )
    name = models.CharField(max_length=100)
    strategy_type = models.CharField(max_length=20, choices=STRATEGY_TYPES)
    min_confidence = models.FloatField(default=70.0)
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Trade(models.Model):
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('WON', 'Won'),
        ('LOST', 'Lost'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    user_bot = models.ForeignKey(UserBot, on_delete=models.SET_NULL, null=True, blank=True, related_name='trades')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trades')
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    direction = models.CharField(max_length=25)  
    stake = models.DecimalField(max_digits=12, decimal_places=2)
    entry_price = models.DecimalField(max_digits=18, decimal_places=8)
    exit_price = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    target_digit = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    payout = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    date_opened = models.DateTimeField(auto_now_add=True)
    date_closed = models.DateTimeField(null=True, blank=True)
    sl = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True, help_text="Stop Loss price")
    tp = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True, help_text="Take Profit price")
    class Meta:
        ordering = ['-date_opened']

    def __str__(self):
        return f"{self.user.username} - {self.asset.symbol} ({self.direction}) [{self.status}]"


class PriceAlert(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    target_price = models.DecimalField(max_digits=18, decimal_places=8)
    condition = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} Alert: {self.asset.symbol} @ {self.target_price}"


class SentimentSignal(models.Model):
    SIGNAL_CHOICES = [
        ('BUY', 'Bullish / Buy'),
        ('SELL', 'Bearish / Sell'),
        ('NEUTRAL', 'Neutral / Hold'),
    ]

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="sentiment_signals", null=True, blank=True)
    asset_symbol = models.CharField(max_length=20, default="XAU/USD")
    query = models.CharField(max_length=255)
    composite_score = models.FloatField()
    signal = models.CharField(max_length=10, choices=SIGNAL_CHOICES)
    confidence = models.FloatField(default=0.0)
    articles_analyzed = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.asset_symbol} - {self.signal} ({self.composite_score:.2f}) @ {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class NewsArticle(models.Model):
    sentiment_signal = models.ForeignKey(SentimentSignal, on_delete=models.CASCADE, related_name='articles')
    title = models.CharField(max_length=500)
    link = models.URLField(max_length=1000)
    published = models.CharField(max_length=100, blank=True, null=True)
    sentiment = models.CharField(max_length=20)
    polarity = models.FloatField()

    def __str__(self):
        return self.title

class UserBrokerAccount(models.Model):
    BROKER_CHOICES = [
        ('DERIV', 'Deriv Account'),
        ('PEPPERSTONE_MT5', 'Pepperstone MetaTrader 5'),
        ('PEPPERSTONE_CTRADER', 'Pepperstone cTrader'),
        ('BINANCE', 'Binance Spot'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='broker_accounts')
    broker = models.CharField(max_length=50, choices=BROKER_CHOICES, default='DERIV')
    account_number = models.CharField(max_length=100)
    server_name = models.CharField(max_length=100, blank=True, null=True, default='Deriv-Server')
    api_token = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ==========================================
    # NEW — Balance Cache Fields
    # ==========================================
    last_known_balance = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        help_text="Cached balance from last successful sync"
    )
    last_balance_currency = models.CharField(max_length=10, default='USD')
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(
        max_length=20, default='PENDING',
        choices=[('OK', 'OK'), ('ERROR', 'Error'), ('PENDING', 'Pending')]
    )
    sync_error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_broker_display()} ({self.account_number})"

    @property
    def is_stale(self):
        """Returns True if last sync is more than 60 seconds old"""
        if not self.last_synced_at:
            return True
        from django.utils import timezone
        from datetime import timedelta
        return (timezone.now() - self.last_synced_at) > timedelta(seconds=60)


# ==========================================
# NEW MODEL — Balance History Snapshots
# ==========================================
class BrokerBalanceSnapshot(models.Model):
    """Stores historical balance snapshots for charts and audit"""
    broker_account = models.ForeignKey(
        UserBrokerAccount, on_delete=models.CASCADE, related_name='balance_snapshots'
    )
    balance = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return f"{self.broker_account} @ {self.balance} {self.currency} ({self.recorded_at})"

# ==========================================
# ADMIN HUB APPROVAL MODELS (ADDED)
# ==========================================

class Deposit(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposits')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=255, unique=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Deposit #{self.id} - {self.user.username} (${self.amount})"


class Withdrawal(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    destination = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Withdrawal #{self.id} - {self.user.username} (${self.amount})"


class KYCVerification(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kyc_verifications')
    document_type = models.CharField(max_length=100, default='National ID')
    document_file = models.FileField(upload_to='kyc_documents/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"KYC - {self.user.username} ({self.document_type})"


class Account(models.Model):
    ACCOUNT_TYPES = (
        ('EXCHANGE', 'Exchange Account'),
        ('TRADING', 'Trading Account'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accounts')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='EXCHANGE')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'account_type')

    def __str__(self):
        return f"@{self.user.username} - {self.get_account_type_display()} (${self.balance})"


class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('INTERNAL_TRANSFER', 'Internal Transfer'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=50) 
    details = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_notified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} of {self.amount}"


class FundedAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='funded_accounts')
    initial_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_funded = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Funded Account for {self.user.username} - Balance: ${self.balance}"


class PaymentRequest(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PROCESSING', 'Processing'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_requests')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=50)
    payment_method = models.CharField(max_length=50, help_text="e.g., M-Pesa, BTC, USDT")
    provider_reference = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def details(self):
        if self.provider_reference:
            return f"{self.transaction_type} via {self.payment_method} (Ref: {self.provider_reference})"
        return f"{self.transaction_type} via {self.payment_method}"

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} ${self.amount} ({self.payment_method})"


class MpesaPayment(models.Model):
    payment_request = models.OneToOneField(PaymentRequest, on_delete=models.CASCADE, related_name='mpesa_details', null=True, blank=True)
    merchant_request_id = models.CharField(max_length=100)
    checkout_request_id = models.CharField(max_length=100)
    result_code = models.IntegerField(null=True, blank=True)
    result_desc = models.TextField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    mpesa_receipt_number = models.CharField(max_length=100, blank=True)
    transaction_date = models.DateTimeField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Mpesa: {self.mpesa_receipt_number or 'Pending'} ({self.checkout_request_id})"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Webhook(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=[('IN', 'Incoming'), ('OUT', 'Outgoing')])
    url = models.URLField()
    method = models.CharField(max_length=10, default='POST')
    is_active = models.BooleanField(default=True)
    requests_count = models.IntegerField(default=0)
    success_rate = models.FloatField(default=100.0)
    latency = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class WebhookLog(models.Model):
    source = models.CharField(max_length=50, default='Generic')
    payload = models.TextField()
    headers = models.TextField(blank=True, null=True)
    is_processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Webhook [{self.source}] at {self.received_at} - {'Success' if self.is_processed else 'Failed'}"

    def get_json_payload(self):
        try:
            return json.loads(self.payload)
        except json.JSONDecodeError:
            return {}


class SiteSettings(models.Model):
    default_trade_amount = models.DecimalField(max_digits=12, decimal_places=2, default=10.00)
    min_trade_amount = models.DecimalField(max_digits=12, decimal_places=2, default=1.00)
    max_trade_amount = models.DecimalField(max_digits=12, decimal_places=2, default=1000.00)
    payout_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=90.00)
    trading_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Trading Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class WebhookEndpoint(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='webhook_endpoints')
    name = models.CharField(max_length=100)
    url = models.URLField(max_length=500)
    is_active = models.BooleanField(default=True)
    requests_count = models.PositiveIntegerField(default=0)
    success_rate = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    latency = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"


class BotLog(models.Model):
    LOG_LEVELS = [
        ('INFO', 'Info'),
        ('BUY', 'Buy Signal'),
        ('SELL', 'Sell Signal'),
        ('WARN', 'Warning'),
        ('ERROR', 'Error'),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, choices=LOG_LEVELS, default='INFO')
    message = models.TextField()

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.level}: {self.message}"


# ==========================================
# MODEL SIGNALS
# ==========================================

@receiver(post_save, sender=Transaction)
def update_account_balance(sender, instance, created, **kwargs):
    if created:
        # Skip internal transfers as they are explicitly managed between accounts in the view
        if instance.transaction_type == 'INTERNAL_TRANSFER':
            return

        # Direct external funds (deposits/withdrawals) target the main EXCHANGE account
        account, _ = Account.objects.get_or_create(user=instance.user, account_type='EXCHANGE')
        credit_types = ['DEPOSIT', 'TRADE_PAYOUT', 'BONUS', 'ADJUSTMENT']
        debit_types = ['WITHDRAWAL', 'TRADE_STAKE']

        if instance.transaction_type in credit_types or instance.transaction_type.startswith('SUB_'):
            account.balance += instance.amount
        elif instance.transaction_type in debit_types:
            account.balance -= instance.amount
        
        account.save()


@receiver(post_save, sender=PaymentRequest)
def handle_payment_approval(sender, instance, **kwargs):
    if instance.status == 'APPROVED' and not instance.processed:
        tier_capital_mapping = {
            'STARTER': 0.00,
            'PRO': 50000.00,
            'VIP': 200000.00,
        }

        purchased_tier = 'PRO'
        if 'VIP' in str(instance.details).upper() or 'VIP' in str(instance.transaction_type).upper():
            purchased_tier = 'VIP'
        elif 'PRO' in str(instance.details).upper() or 'PRO' in str(instance.transaction_type).upper():
            purchased_tier = 'PRO'
        elif 'STARTER' in str(instance.details).upper() or 'STARTER' in str(instance.transaction_type).upper():
            purchased_tier = 'STARTER'

        assigned_capital = tier_capital_mapping.get(purchased_tier, 50000.00)

        profile, _ = UserProfile.objects.get_or_create(user=instance.user)
        profile.subscription_tier = purchased_tier.lower()
        profile.is_active_subscription = (purchased_tier != 'STARTER')
        profile.save()

        funded_account, _ = FundedAccount.objects.get_or_create(user=instance.user)
        funded_account.is_funded = (assigned_capital > 0)
        funded_account.initial_balance = assigned_capital
        funded_account.balance = assigned_capital
        funded_account.save()

        Transaction.objects.create(
            user=instance.user,
            amount=instance.amount,
            transaction_type=f'SUB_{purchased_tier}',
            details=f"Subscription Payment - {purchased_tier} Tier (Funded: ${assigned_capital:,.2f})"
        )

        instance.processed = True
        instance.save()


@receiver(post_save, sender=Transaction)
def send_transaction_notification(sender, instance, created, **kwargs):
    if created and instance.transaction_type == 'DEPOSIT':
        Notification.objects.create(
            user=instance.user,
            title="Transaction Approved",
            message=f"Your deposit of ${instance.amount} was successful."
        )



class ClientAIToggle(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    assigned_lot_size = models.DecimalField(max_digits=5, decimal_places=2, default=1.00)
    last_trade_date = models.DateField(null=True, blank=True) # Tracks daily execution
    
    def __str__(self):
        return f"{self.user.username} - Active: {self.is_active}"


class SurveyReward(models.Model):
    TIER_CHOICES = [
        ('PRO', 'Pro'),
        ('VIP', 'VIP'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='survey_rewards')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    tier_required = models.CharField(max_length=10, choices=TIER_CHOICES, default='PRO')
    is_claimed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - ${self.amount} ({self.user.username})"



import logging
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

# Complete asset universe: Gold, US Oil, EUR/GBP/JPY crosses, and Bitcoin
ASSET_UNIVERSE = {
    "commodities": ["XAUUSD", "USOIL"],
    "forex_pairs": [
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "EURGBP",
        "EURJPY",
        "GBPJPY",
    ],
    "crypto": ["BTCUSD"],
}


def fetch_market_data(symbol, timeframe="1h", limit=100):
  """Fetch historical OHLCV data for the specified symbol."""
  # TODO: Integrate with broker API (e.g., MetaTrader, Deriv, Pepperstone, or CCXT)
  pass


def calculate_broker_parameters(symbol, current_price):
  """Calculate precise broker-grade Stop Loss, Take Profit, and Lot sizing based on asset class volatility."""
  if "XAU" in symbol:
    volume = 1.00
    sl_distance = 15.00  # $15.00 price distance for Gold
    tp_distance = 30.00
    spread = "1.2 pips"
  elif "BTC" in symbol:
    volume = 0.10
    sl_distance = 500.00  # $500 price distance for Bitcoin
    tp_distance = 1200.00
    spread = "12.0 pts"
  elif "OIL" in symbol:
    volume = 1.00
    sl_distance = 1.20  # $1.20 price distance for WTI Oil
    tp_distance = 2.50
    spread = "0.03 pts"
  else:  # Forex Majors & Crosses (EUR, GBP, JPY)
    volume = 0.50
    sl_distance = 0.0035  # 35 pips
    tp_distance = 0.0070  # 70 pips
    spread = "1.0 pip"

  # Determine exact SL and TP price triggers for Buy orders
  sl_price = round(current_price - sl_distance, 5)
  tp_price = round(current_price + tp_distance, 5)

  return {
      "volume": volume,
      "sl": sl_price,
      "tp": tp_price,
      "spread": spread,
  }


def analyze_market_conditions(df, symbol):
  """Generate professional technical signals using pandas-ta indicators."""
  if df is None or len(df) < 200:
    return "HOLD"

  # Technical Analysis indicators computation
  df["rsi"] = ta.rsi(df["close"], length=14)
  df["sma_50"] = ta.sma(df["close"], length=50)
  df["sma_200"] = ta.sma(df["close"], length=200)

  last = df.iloc[-1]
  prev = df.iloc[-2]

  is_bullish_trend = last["close"] > last["sma_50"] > last["sma_200"]
  is_bearish_trend = last["close"] < last["sma_50"] < last["sma_200"]

  rsi_bullish = prev["rsi"] <= 45 and last["rsi"] > 45
  rsi_bearish = prev["rsi"] >= 55 and last["rsi"] < 55

  if is_bullish_trend and rsi_bullish:
    return "BUY"
  elif is_bearish_trend and rsi_bearish:
    return "SELL"

  return "HOLD"


def execute_broker_order(symbol, order_type, current_price, params):
  """Simulates broker execution ticket logging with full risk parameters."""
  logger.info(
      f"[BROKER EXECUTION] Ticket Created | Symbol: {symbol} | Type:"
      f" {order_type} | Volume: {params['volume']} | Entry: {current_price} |"
      f" SL: {params['sl']} | TP: {params['tp']} | Spread: {params['spread']}"
  )
  # TODO: Insert Django ORM order logging and broker API integration here
  return {
      "ticket_id": "#ORD-" + str(pd.Timestamp.now().timestamp())[-6:],
      "symbol": symbol,
      "type": order_type,
      "volume": params["volume"],
      "entry": current_price,
      "sl": params["sl"],
      "tp": params["tp"],
      "status": "FILLED",
  }


def run_daily_ai_gold_engine():
  """Main multi-asset automated engine handling commodities, forex, and crypto with full broker specs."""
  logger.info("Initializing institutional multi-asset trading engine...")

  all_symbols = (
      ASSET_UNIVERSE["commodities"]
      + ASSET_UNIVERSE["forex_pairs"]
      + ASSET_UNIVERSE["crypto"]
  )
  active_portfolio = list(set(all_symbols))
  engine_report = {}

  for symbol in active_portfolio:
    try:
      df = fetch_market_data(symbol)
      signal = analyze_market_conditions(df, symbol)
      engine_report[symbol] = signal

      if signal in ["BUY", "SELL"]:
        current_price = df.iloc[-1]["close"]
        params = calculate_broker_parameters(symbol, current_price)

        # Invert SL/TP logic if a SELL signal is triggered
        if signal == "SELL":
          params["sl"] = round(current_price + (current_price - params["sl"]), 5)
          params["tp"] = round(current_price - (params["tp"] - current_price), 5)

        order_receipt = execute_broker_order(
            symbol, signal, current_price, params
        )
        logger.info(f"Successfully processed order for {symbol}: {order_receipt}")

    except Exception as e:
      logger.error(
          f"Execution error encountered for asset group {symbol}: {str(e)}"
      )

  logger.info("Multi-asset trading engine run completed successfully.")
  return engine_report



from django.contrib.auth.models import User
from django.db import models


class KYCProfile(models.Model):
  STATUS_CHOICES = [
      ('PENDING', 'Pending'),
      ('APPROVED', 'Approved'),
      ('REJECTED', 'Rejected'),
  ]
  user = models.ForeignKey(User, on_delete=models.CASCADE)
  status = models.CharField(
      max_length=20, choices=STATUS_CHOICES, default='PENDING'
  )
  document_type = models.CharField(max_length=50)
  document_number = models.CharField(max_length=100)
  document_image = models.ImageField(upload_to='kyc_documents/')
  submitted_at = models.DateTimeField(auto_now_add=True)

  def __str__(self):
    return f'{self.user.username} - {self.document_type} ({self.status})'


class TradingAccount(models.Model):
  user = models.ForeignKey(User, on_delete=models.CASCADE)
  account_id = models.CharField(
      max_length=50, unique=True, blank=True, null=True
  )
  type = models.CharField(max_length=50, default='Live')
  balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
  leverage = models.IntegerField(default=100)
  margin_level = models.FloatField(default=150.0)

  def __str__(self):
    return (
        f'{self.user.username} - {self.account_id or self.id}'
        f' (${self.balance})'
    )


class TradePosition(models.Model):
  BOOK_CHOICES = [('A_BOOK', 'A-Book'), ('B_BOOK', 'B-Book')]
  STATUS_CHOICES = [('OPEN', 'Open'), ('CLOSED', 'Closed')]

  user = models.ForeignKey(User, on_delete=models.CASCADE)
  notional_value = models.DecimalField(max_digits=12, decimal_places=2)
  liability = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
  execution_book = models.CharField(
      max_length=20, choices=BOOK_CHOICES, default='B_BOOK'
  )
  status = models.CharField(
      max_length=20, choices=STATUS_CHOICES, default='OPEN'
  )
  created_at = models.DateTimeField(auto_now_add=True)


class TransactionLog(models.Model):
  STATUS_CHOICES = [
      ('SUCCESS', 'Success'),
      ('PENDING', 'Pending'),
      ('DISCREPANCY', 'Discrepancy'),
  ]
  user = models.ForeignKey(
      User, on_delete=models.SET_NULL, null=True, blank=True
  )
  reference_id = models.CharField(max_length=100, unique=True)
  gateway_name = models.CharField(max_length=50)
  transaction_type = models.CharField(max_length=50)
  amount = models.DecimalField(max_digits=12, decimal_places=2)
  status = models.CharField(
      max_length=20, choices=STATUS_CHOICES, default='PENDING'
  )
  created_at = models.DateTimeField(auto_now_add=True)


class KYCProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='PENDING')
    document_type = models.CharField(max_length=50, default='National ID')
    id_number = models.CharField(max_length=50, blank=True, null=True)
    document_file = models.FileField(upload_to='kyc_documents/', blank=True, null=True)
    selfie_image = models.ImageField(upload_to='kyc_selfies/', blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.status}"


from django.db import models
from django.contrib.auth.models import User

class SupportTicket(models.Model):
    CATEGORY_CHOICES = [
        ('AI Signals & Execution', 'AI Signals & Execution'),
        ('Subscription & Billing', 'Subscription & Billing'),
        ('Webhook & Bot Integration', 'Webhook & Bot Integration'),
        ('Account & Security', 'Account & Security'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES)
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=50, default='Open')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.category}] {self.subject} ({self.status})"
    



# Add to models.py

class FundedTrade(models.Model):
    """Tracks trades executed from funded accounts via AI Gold Auto-Trader"""
    funded_account = models.ForeignKey('FundedAccount', on_delete=models.CASCADE, related_name='trades')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    asset = models.CharField(max_length=20, default='XAUUSD')
    direction = models.CharField(max_length=10)  # BUY or SELL
    entry_price = models.DecimalField(max_digits=18, decimal_places=2)
    exit_price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    lot_size = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    profit_percent = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # 88% of actual profit
    profit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, default='PENDING')  # PENDING, WON, LOST
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.asset} ({self.direction}) - {self.status}"
    

# models.py - add this to your existing models

class UserSession(models.Model):
    """Tracks user login sessions for security management"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_sessions')
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    device_type = models.CharField(max_length=20, default='desktop')  # desktop, mobile, tablet
    browser = models.CharField(max_length=50, default='Unknown')
    os_name = models.CharField(max_length=50, default='Unknown')
    location = models.CharField(max_length=100, blank=True, null=True)
    is_current = models.BooleanField(default=False)
    last_activity = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_activity']

    def __str__(self):
        return f"{self.user.username} - {self.browser} on {self.os_name}"