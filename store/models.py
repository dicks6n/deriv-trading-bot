from django.db import models
from django.conf import settings


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


        # store/models.py
from django.db import models
from django.contrib.auth.models import User

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