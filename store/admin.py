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