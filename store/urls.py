from django.urls import path
from . import views

urlpatterns = [
    # Main Dashboard
    path('', views.dashboard_view, name='dashboard'),  # Sets as home page (http://127.0.0.1:8000/)
    path('', views.market_dashboard, name='home'),
    path('index/', views.market_dashboard, name='index'),
    path('market-overview/', views.market_overview_view, name='market_overview'),  # Add this route
    # API & Trade Execution
    path('api/analysis/<int:asset_id>/', views.ai_analysis_api, name='ai_analysis_api'),
    path('open-trade/', views.open_trade, name='open_trade'),
    path('history/', views.trade_history, name='trade_history'),
    path('api/check-notifications/', views.check_notifications, name='check_notifications'),
    path('webhooks/', views.webhook_automations, name='webhooks'),
    path('trade/execute/', views.execute_trade, name='execute_trade'),
    path('webhook-automations/', views.webhook_automations, name='webhook_automations'),
    path('webhook-automations/create/', views.create_webhook, name='create_webhook'),
    # store/urls.py
    path('automations/webhooks/', views.webhook_automations_view, name='webhook_automations'),
    path('automations/webhooks/<int:webhook_id>/toggle/', views.toggle_webhook_status, name='toggle_webhook'),
# project/urls.py
    path('bot/', views.bot_dashboard_view, name='bot'),  # <-- Ensure name is 'bot'
    path('bot/control/', views.bot_control_view, name='bot_control'),
    path('bot/create/', views.create_bot_view, name='create_bot'),
    
    # URL endpoint for processing button actions (POST only)
    path('bot/control/', views.bot_control_view, name='bot_control'),
    path('payments/status/', views.payment_status_view, name='payment_status'),
    path('account-operations/funding/payment-methods/deposit', views.funding_deposit, name='funding_deposit'),
    path('deriv-callback/', views.deriv_callback, name='deriv_callback'),
    path('admin/deposits/', views.admin_deposit_approval_view, name='admin_deposit_approval'),
    path('request-deposit/', views.request_deposit, name='request_deposit'),
    path('request-withdrawal/', views.request_withdrawal, name='request_withdrawal'),
    path('digits_trading/', views.digits_trading, name='digits_trading'),
    path('deposit/', views.request_deposit, name='request_deposit'),
    path('api/payment-status/<str:checkout_id>/', views.check_payment_status, name='check_payment_status'),
    path('funded/', views.funded_view, name='funded'),
    path('trade/', views.trade_view, name='trade'),
    # AI & Signals
    path('live-signals/', views.live_signals, name='live_signals'),
    path('ai-generator/', views.ai_signal_generator, name='ai_signal_generator'),
    path('market-overview/', views.market_overview, name='markets'),
    path('ai-summary/', views.ai_market_summary, name='ai_market_summary'),
    path('prediction-models/', views.ai_prediction_models, name='ai_prediction_models'),
    path('risk-analyzer/', views.ai_risk_analyzer, name='ai_risk_analyzer'),
    path('trade-journal/', views.ai_trade_journal, name='ai_trade_journal'),
    path('strategy-builder/', views.ai_strategy_builder, name='ai_strategy_builder'),
    path('run-sentiment/', views.run_sentiment_analysis_view, name='run_sentiment_analysis'),
    # Charts & Analytics
    path('forex-heatmap/', views.forex_heatmap, name='forex_heatmap'),
    path('crypto-heatmap/', views.crypto_heatmap, name='crypto_heatmap'),
    path('trend-scanner/', views.trend_scanner, name='trend_scanner'),
    path('pattern-detection/', views.pattern_detection, name='pattern_detection'),
    path('volatility-index/', views.volatility_index, name='volatility_index'),
    path('economic-calendar/', views.economic_calendar, name='economic_calendar'),
    path('news-sentiment/', views.news_sentiment, name='news_sentiment'),
    path('correlation-matrix/', views.correlation_matrix, name='correlation_matrix'),
    path('forex-analytics/', views.forex_analytics, name='forex_analytics'),
    path('crypto-analytics/', views.crypto_analytics, name='crypto_analytics'),
    path('top-gainers-losers/', views.top_gainers_losers, name='top_gainers_losers'),
    path('market-sentiment/', views.market_sentiment, name='market_sentiment'),
    path('liquidity-zones/', views.liquidity_zones, name='liquidity_zones'),
    path('price-action/', views.price_action_monitor, name='price_action_monitor'),

    # Portfolio & Trading
    path('portfolio/', views.user_trades, name='my_trades'),
    path('portfolio-overview/', views.user_trades, name='portfolio'),
    path('open-positions/', views.open_positions, name='open_positions'),
    path('trade-history/', views.trade_history, name='trade_history'),
    path('performance/', views.performance_analytics, name='performance_analytics'),
    path('risk-metrics/', views.risk_metrics, name='risk_metrics'),
    path('pl-overview/', views.pl_overview, name='pl_overview'),
    path('forex-pairs/', views.forex_pairs, name='forex_pairs'),
    path('crypto-pairs/', views.crypto_pairs, name='crypto_pairs'),

    # Automation & Settings
    path('custom-alerts/', views.custom_alerts, name='custom_alerts'),
    path('saved-signals/', views.saved_signals, name='saved_signals'),
    path('bot-center/', views.bot_center, name='bot_center'),
    path('auto-signal-forwarder/', views.auto_signal_forwarder, name='auto_signal_forwarder'),
    path('webhook-automations/', views.webhook_automations, name='webhook_automations'),
    path('api-integrations/', views.api_integrations, name='api_integrations'),
    path('profile-security/', views.profile_security, name='profile_security'),
    path('notifications/', views.notification_settings, name='notification_settings'),
    path('connected-exchanges/', views.connected_exchanges, name='connected_exchanges'),
    path('subscription/', views.subscription_billing, name='subscription_billing'),
    path('help-center/', views.help_center, name='help_center'),
    path('account-operations/funding/payment-methods/deposit/mpesa-callback/', views.mpesa_callback, name='mpesa_callback'),
    path('admin-payments/', views.admin_payment_dashboard, name='admin_payment_dashboard'),
    path('deposit/request/', views.request_deposit, name='request_deposit'),
# Deriv OAuth & Manual Connect Routes
    path('connect-deriv/', views.connect_deriv, name='connect_deriv'),
    path('connect-broker/', views.connect_broker, name='connect_broker'),
    path('deriv-callback/', views.deriv_callback, name='deriv_callback'),


    path('subscription/', views.subscription_billing, name='subscription_billing'),
    # API & Execution
    path('api/analysis/<int:asset_id>/', views.ai_analysis_api, name='ai_analysis_api'),
    path('open-trade/', views.open_trade, name='open_trade'),
    # Auth
    path('api/webhooks/<str:source_name>/', views.handle_incoming_webhook, name='incoming_webhook'),
    path('profile/', views.profile, name='profile'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
]

