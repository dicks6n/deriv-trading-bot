# store/models.py
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.db.models.signals import post_save
from decimal import Decimal

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subscription_tier = models.CharField(max_length=50, default='free')

    def __str__(self):
        return self.user.username


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

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    direction = models.CharField(max_length=15)  # e.g., BUY, SELL, EVEN, ODD, OVER, UNDER, DIFFER
    stake = models.DecimalField(max_digits=12, decimal_places=2, default=10.00)
    entry_price = models.DecimalField(max_digits=18, decimal_places=8)
    exit_price = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    target_digit = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    payout = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    date_opened = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_opened']

    def __str__(self):
        return f"{self.user.username} - {self.asset.symbol} ({self.direction}) [{self.status}]"


class PriceAlert(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    target_price = models.DecimalField(max_digits=18, decimal_places=8)
    condition = models.CharField(max_length=20)  # e.g., ABOVE, BELOW
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} Alert: {self.asset.symbol} @ {self.target_price}"


# ==========================================
# AI SENTIMENT PREDICTION MODELS
# ==========================================

class SentimentSignal(models.Model):
    SIGNAL_CHOICES = [
        ('BUY', 'Bullish / Buy'),
        ('SELL', 'Bearish / Sell'),
        ('NEUTRAL', 'Neutral / Hold'),
    ]

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="sentiment_signals", null=True, blank=True)
    asset_symbol = models.CharField(max_length=20, default="XAU/USD")
    query = models.CharField(max_length=255)
    composite_score = models.FloatField()  # Score from -1.0 to +1.0
    signal = models.CharField(max_length=10, choices=SIGNAL_CHOICES)
    confidence = models.FloatField(default=0.0)  # Percentage (e.g. 85.0)
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
    sentiment = models.CharField(max_length=20)  # Positive, Negative, Neutral
    polarity = models.FloatField()

    def __str__(self):
        return self.title


# ==========================================
# FINANCIAL & PAYMENT MODELS
# ==========================================

class UserBrokerAccount(models.Model):
    BROKER_CHOICES = [
        ('DERIV', 'Deriv Account'),
        ('PEPPERSTONE_MT5', 'Pepperstone MetaTrader 5'),
        ('PEPPERSTONE_CTRADER', 'Pepperstone cTrader'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='broker_accounts')
    broker = models.CharField(max_length=50, choices=BROKER_CHOICES, default='DERIV')
    account_number = models.CharField(max_length=100) # e.g. CR123456 or VRTC123456
    server_name = models.CharField(max_length=100, blank=True, null=True, default='Deriv-Server')
    api_token = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_broker_display()} ({self.account_number})"


class Account(models.Model):
    """Stores the current state of the user's balance."""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.user.username} - Balance: {self.balance}"


class Transaction(models.Model):
    """Stores the history of all successful deposits and withdrawals."""
    TRANSACTION_TYPES = (
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    details = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_notified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} of {self.amount}"

# Signal: Update Balance when a Transaction is saved
@receiver(post_save, sender=Transaction)
def update_account_balance(sender, instance, created, **kwargs):
    if created:
        account, _ = Account.objects.get_or_create(user=instance.user)
        if instance.transaction_type == 'DEPOSIT':
            account.balance += instance.amount
        elif instance.transaction_type == 'WITHDRAWAL':
            account.balance -= instance.amount
        account.save()    


class PaymentRequest(models.Model):
    """Stores requests for deposits (pending admin approval or API response)."""
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PROCESSING', 'Processing (e.g., STK Push sent)'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Using specific names to avoid Python reserved word conflicts
    transaction_type = models.CharField(max_length=20, default='DEPOSIT')
    payment_method = models.CharField(max_length=50, default='M-Pesa')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

# Signal: Handle deposit approval (updates account and creates transaction)
# store/models.py

class MpesaPayment(models.Model):
    """Stores raw data from M-Pesa STK Push / C2B callbacks."""
    payment_request = models.OneToOneField(PaymentRequest, on_delete=models.CASCADE, related_name='mpesa_details', null=True, blank=True)
    merchant_request_id = models.CharField(max_length=100)
    checkout_request_id = models.CharField(max_length=100)
    result_code = models.IntegerField(null=True, blank=True)  # Updated to allow initial nulls
    result_desc = models.TextField(null=True, blank=True)     # Updated to allow initial nulls
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    mpesa_receipt_number = models.CharField(max_length=100, blank=True)
    transaction_date = models.DateTimeField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Mpesa: {self.mpesa_receipt_number or 'Pending'} ({self.checkout_request_id})"

# Signal: Handle deposit approval (updates account and creates transaction)
@receiver(post_save, sender=PaymentRequest)
def handle_payment_approval(sender, instance, **kwargs):
    if instance.status == 'APPROVED' and not instance.processed:
        account, created = Account.objects.get_or_create(user=instance.user)
        account.balance += instance.amount
        account.save()
        
        Transaction.objects.create(
            user=instance.user,
            amount=instance.amount,
            transaction_type='DEPOSIT',
            details=f"M-Pesa Deposit - {instance.payment_method}"
        )
        
        instance.processed = True
        instance.save()

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

@receiver(post_save, sender=Transaction)
def send_transaction_notification(sender, instance, created, **kwargs):
    # Create notification only on deposit approval (withdrawals are handled by admin workflow or API)
    if instance.transaction_type == 'DEPOSIT':
        title = "Transaction Approved"
        message = f"Your {instance.transaction_type.lower()} of ${instance.amount} was successful."
        
        Notification.objects.create(
            user=instance.user,
            title=title,
            message=message
        )


class Webhook(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=[('IN', 'Incoming'), ('OUT', 'Outgoing')])
    url = models.URLField()
    method = models.CharField(max_length=10, default='POST')
    is_active = models.BooleanField(default=True)
    requests_count = models.IntegerField(default=0)
    success_rate = models.FloatField(default=100.0)
    latency = models.IntegerField(default=0) # in ms
    created_at = models.DateTimeField(auto_now_add=True)


class WebhookLog(models.Model):
    """Logs incoming webhooks for auditing and automation triggers."""
    source = models.CharField(max_length=50, default='Generic')  # e.g., 'TradingView', 'Binance'
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
    """
    Singleton model for site-wide trading configuration.
    Edited from the Django admin. All 'site trading' (simulated trades settled
    against the user's internal Account balance) reads its stake defaults and
    limits from here instead of hardcoded values.
    """
    default_trade_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=10.00,
        help_text="Stake used for a trade when the trader doesn't specify one."
    )
    min_trade_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=1.00,
        help_text="Smallest stake a trader is allowed to place."
    )
    max_trade_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=1000.00,
        help_text="Largest stake a trader is allowed to place."
    )
    payout_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=90.00,
        help_text="House payout on a winning trade. 90.00 means a $10 winning "
                   "stake returns $19.00 total (stake + 90% profit)."
    )
    trading_enabled = models.BooleanField(
        default=True,
        help_text="Site-wide kill switch. Turn off to pause all new trade execution."
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Trading Settings"

    def save(self, *args, **kwargs):
        # Enforce singleton: there is only ever one row, with pk=1.
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Prevent the singleton row from being deleted via admin/shell.
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
    success_rate = models.DecimalField(max_digits=5, decimal_places=2, default=100.00) # e.g., 99.80%
    latency = models.PositiveIntegerField(default=0)  # Measured in milliseconds (ms)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"




from django.db import models

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