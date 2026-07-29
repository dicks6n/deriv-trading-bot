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
# project/urls.py
    path('deriv-callback/', views.deriv_callback, name='deriv_callback'),
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



# Deriv OAuth & Manual Connect Routes
    path('connect-deriv/', views.connect_deriv, name='connect_deriv'),
    path('connect-broker/', views.connect_broker, name='connect_broker'),
    path('deriv-callback/', views.deriv_callback, name='deriv_callback'),

    # API & Execution
    path('api/analysis/<int:asset_id>/', views.ai_analysis_api, name='ai_analysis_api'),
    path('open-trade/', views.open_trade, name='open_trade'),
    # Auth
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
]

