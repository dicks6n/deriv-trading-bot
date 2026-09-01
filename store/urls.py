from django.urls import path
from . import views
from store.views import cryptomus_verify , landing_page_view
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomTokenObtainPairSerializer

#app_name = 'store'

urlpatterns = [
    # Main Dashboard & Home
    #path('', views.landing_page_view, name='landing'),
    path('', views.dashboard_view, name='dashboard'),
    path('dashboard/', views.landing_page_view, name='landing'),
    path('index/', views.dashboard_view, name='index'),
    path('market-overview/', views.market_overview_view, name='market_overview'),
    path('markets/', views.market_overview, name='markets'),

    # MetaTrader & Trading Accounts (New Broker Suite)
    path('accounts/', views.trading_accounts_view, name='trading_accounts'),
    path('accounts/leverage/', views.account_leverage_view, name='account_leverage'),
    path('platforms/download/', views.platforms_download_view, name='platforms_download'),
    path('trading-accounts/', views.trading_accounts_view, name='trading_accounts'),

    # KYC & Compliance Suite (New)
    path('kyc/submit/', views.kyc_submit_view, name='kyc_submit'),
    path('kyc/status/', views.kyc_status_view, name='kyc_status'),
# urls.py snippet
    path('admin/messages/', views.admin_message_center_view, name='admin_message_center'),
    path('support/', views.ai_support_view, name='ai_support'),
    
    path('support/ticket/submit/', views.submit_support_ticket, name='submit_support_ticket'),
    # Crypto Wallet, Deposits, Withdrawals & Gateways (Expanded)
    path('wallet/crypto/', views.crypto_wallet_view, name='crypto_wallet'),
    path('wallet/crypto/deposit/', views.crypto_deposit_view, name='crypto_deposit'),
    path('wallet/crypto/withdrawal/', views.crypto_withdrawal_view, name='crypto_withdrawal'),
    path('gateway/callback/', views.gateway_callback_view, name='gateway_callback'),
    path('deposit/', views.request_deposit, name='request_deposit'),
    path('deposit/create/', views.create_nowpayments_payment, name='create_nowpayments_payment'),
    path('deposit/request/', views.request_deposit, name='request_deposit'),
    path('deposit/status/<str:payment_id>/', views.payment_status_view, name='funding_status'),
    path('deposit/crypto/submit/', views.submit_crypto_deposit, name='submit_crypto_deposit'),
    path('funding/withdrawal/', views.request_withdrawal, name='request_withdrawal'),
    path('funding/transfer/', views.internal_transfer, name='internal_transfer'),
    path('transfer-accounts/', views.transfer_between_accounts, name='transfer_between_accounts'),
    path('payments/status/', views.payment_status_view, name='payment_status'),
    path('api/payment-status/<str:checkout_id>/', views.check_payment_status, name='check_payment_status'),
    path('account-operations/funding/payment-methods/deposit', views.funding_deposit, name='funding_deposit'),
    path('account-operations/funding/payment-methods/deposit/mpesa-callback/', views.mpesa_callback, name='mpesa_callback'),

    # Payment Gateways & Webhooks IPN
    path('api/nowpayments/ipn/', views.nowpayments_ipn_webhook, name='nowpayments_ipn_webhook'),
    path('api/webhook/binance/', views.binance_webhook, name='binance_webhook'),
    path('cryptomus_6fcb4880.html', cryptomus_verify),

    # Developer & API Portal (New)
    #path('developer/api/', views.api_dashboard_view, name='api_dashboard'),
   # path('developer/webhooks/', views.webhook_manager_view, name='webhook_manager'),
   # path('developer/docs/', views.api_docs_view, name='api_docs'),
    path('api-integrations/', views.api_integrations, name='api_integrations'),
    path('api/live-breakout-predictions/', views.get_live_breakout_predictions_api, name='live_breakout_predictions_api'),
    # AI, Signals & Trading Tools
    path('trade/', views.trade_view, name='trade'),
    path('funded/', views.funded_view, name='funded'),
    path('digits_trading/', views.digits_trading, name='digits_trading'),
    path('open-trade/', views.open_trade, name='open_trade'),
    path('trade/execute/', views.execute_trade, name='execute_trade'),
    path('api/analysis/<int:asset_id>/', views.ai_analysis_api, name='ai_analysis_api'),
    path('live-signals/', views.live_signals, name='live_signals'),
    path('ai-generator/', views.ai_signal_generator, name='ai_signal_generator'),
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

    # Portfolio & Trade History
    path('portfolio/', views.user_trades, name='portfolio'),
    path('portfolio-overview/', views.user_trades, name='my_trades'),
    path('open-positions/', views.open_positions, name='open_positions'),
    path('trade-history/', views.trade_history, name='trade_history'),
    path('history/', views.trade_history, name='trade_history_alt'),
    path('performance/', views.performance_analytics, name='performance_analytics'),
    path('risk-metrics/', views.risk_metrics, name='risk_metrics'),
    path('pl-overview/', views.pl_overview, name='pl_overview'),
    path('forex-pairs/', views.forex_pairs, name='forex_pairs'),
    path('crypto-pairs/', views.crypto_pairs, name='crypto_pairs'),

    # Automation, Bots & Webhooks
    path('api/token/', TokenObtainPairView.as_view(serializer_class=CustomTokenObtainPairSerializer), name='token_obtain_pair'),

    path('bot/', views.bot_dashboard_view, name='bot'),
    path('bot/control/', views.bot_control_view, name='bot_control'),
    path('bot/create/', views.create_bot_view, name='create_bot'),
    path('bot-center/', views.bot_center, name='bot_center'),
    path('webhooks/', views.webhook_automations, name='webhooks'),
    path('webhook-automations/', views.webhook_automations, name='webhook_automations'),
    path('webhook-automations/create/', views.create_webhook, name='create_webhook'),
    path('automations/webhooks/', views.webhook_automations_view, name='webhook_automations_view'),
    path('automations/webhooks/<int:webhook_id>/toggle/', views.toggle_webhook_status, name='toggle_webhook'),
    path('api/webhooks/<str:source_name>/', views.handle_incoming_webhook, name='incoming_webhook'),
    path('auto-signal-forwarder/', views.auto_signal_forwarder, name='auto_signal_forwarder'),
    path('custom-alerts/', views.custom_alerts, name='custom_alerts'),
    path('saved-signals/', views.saved_signals, name='saved_signals'),

    # Broker & OAuth Connection
    path('connect-deriv/', views.connect_deriv, name='connect_deriv'),
    path('connect-broker/', views.connect_broker, name='connect_broker'),
    path('deriv-callback/', views.deriv_callback, name='deriv_callback'),

    # Rewards & Subscription
    path('rewards/', views.survey_rewards_view, name='survey_rewards'),
    path('rewards/claim/<int:reward_id>/', views.claim_survey_reward, name='claim_survey_reward'),
    path('subscription/', views.subscription_billing, name='subscription_billing'),
    path('subscription/cancel/', views.cancel_subscription, name='cancel_subscription'),
    path('subscription/switch/<str:tier>/', views.switch_tier, name='switch_tier'),

    # Settings, Profile & Support
    path('profile/', views.profile, name='profile'),
    path('profile-security/', views.profile_security, name='profile_security'),
    path('notifications/', views.notification_settings, name='notification_settings'),
    path('api/check-notifications/', views.check_notifications, name='check_notifications'),
    path('connected-exchanges/', views.connected_exchanges, name='connected_exchanges'),
    path('help-center/', views.help_center, name='help_center'),


    
    path('auth/otp/request/', views.request_email_otp_view, name='request_email_otp'),
    path('auth/otp/verify/', views.verify_email_otp_view, name='verify_email_otp'),
    # Admin & Back-Office Extensions
    path('admin/hub/', views.admin_dashboard_hub_view, name='admin_dashboard_hub'),
    path('admin/kyc/', views.admin_kyc_queue_view, name='admin_kyc_queue'),
    path('admin/risk/', views.admin_risk_dashboard_view, name='admin_risk_dashboard'),
    path('admin/gateways/', views.admin_gateway_logs_view, name='admin_gateway_logs'),
    path('admin-payments/', views.admin_payment_dashboard, name='admin_payment_dashboard'),
    path('admin/kyc/update/<int:pk>/', views.update_kyc_status, name='update_kyc_status'),
    # Authentication
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),


    path('support/', views.ai_support_view, name='ai_support'),
    path('support/ticket/submit/', views.submit_support_ticket, name='submit_support_ticket'),

]