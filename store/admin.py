from django.contrib import admin
from .models import UserProfile, Asset, Trade, PriceAlert, PriceTick, AITradingStrategy


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'subscription_tier')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'name', 'asset_type', 'price', 'change_percent', 'digit_precision')
    list_filter = ('asset_type',)
    search_fields = ('symbol', 'name')


@admin.register(PriceTick)
class PriceTickAdmin(admin.ModelAdmin):
    list_display = ('asset', 'price', 'last_digit', 'timestamp')
    list_filter = ('asset', 'last_digit')
    date_hierarchy = 'timestamp'


@admin.register(AITradingStrategy)
class AITradingStrategyAdmin(admin.ModelAdmin):
    list_display = ('name', 'strategy_type', 'min_confidence', 'is_enabled')


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ('user', 'asset', 'direction', 'stake', 'entry_price', 'status', 'date_opened')
    list_filter = ('status', 'direction')


@admin.register(PriceAlert)
class PriceAlertAdmin(admin.ModelAdmin):
    list_display = ('user', 'asset', 'target_price', 'is_active')

from .models import Account, Transaction  # Ensure these are imported

# Register your models here
@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction_type', 'amount', 'created_at')

# In admin.py
from django.contrib import admin
from .models import PaymentRequest

@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'status', 'processed', 'created_at')
    list_editable = ('status',) # Allows admin to change status directly from the list view

# store/admin.py

from django.contrib import admin
from .models import WebhookEndpoint, WebhookLog

@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'url', 'is_active', 'requests_count', 'success_rate', 'latency')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'url', 'user__username')

@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ('source', 'is_processed', 'received_at')
    list_filter = ('is_processed', 'source', 'received_at')
    search_fields = ('source', 'payload')

from .models import SiteSettings

@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()  # enforce singleton in the UI too
    def has_delete_permission(self, request, obj=None):
        return False