from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
import urllib.parse

from .models import Asset, Trade, UserBrokerAccount, SentimentSignal, NewsArticle
from .deriv_service import DerivService


@login_required
def connect_deriv(request):
    """Redirects user to Deriv OAuth Login page."""
    app_id = getattr(settings, 'DERIV_APP_ID', '1089')
    # Deriv OAuth URL
    deriv_oauth_url = f"https://oauth.deriv.com/oauth2/authorize?app_id={app_id}"
    return redirect(deriv_oauth_url)


@login_required
def deriv_callback(request):
    """
    Handles callback after user authorizes on Deriv OAuth.
    Deriv returns account details as query parameters:
    ?acct1=CR123456&token1=a1-xyz&cur1=USD&acct2=VRTC123456&token2=a1-abc&cur2=USD
    """
    # Deactivate prior active accounts for this user
    UserBrokerAccount.objects.filter(user=request.user, broker='DERIV').update(is_active=False)

    saved_accounts_count = 0
    index = 1

    while True:
        acct_param = f'acct{index}'
        token_param = f'token{index}'
        cur_param = f'cur{index}'

        account_number = request.GET.get(acct_param)
        api_token = request.GET.get(token_param)
        currency = request.GET.get(cur_param, 'USD')

        if not account_number or not api_token:
            break

        is_demo_account = account_number.startswith('VRTC')

        # Create or update user broker account
        UserBrokerAccount.objects.update_or_create(
            user=request.user,
            broker='DERIV',
            account_number=account_number,
            defaults={
                'api_token': api_token,
                'currency': currency,
                'is_demo': is_demo_account,
                'is_active': True if index == 1 else False  # Set first returned account as active
            }
        )
        saved_accounts_count += 1
        index += 1

    if saved_accounts_count > 0:
        messages.success(request, f"Successfully connected {saved_accounts_count} Deriv account(s)!")
    else:
        messages.error(request, "Failed to connect Deriv account. Parameters missing.")

    return redirect('ai_prediction_models')


@login_required
def ai_prediction_models(request):
    """Renders main dashboard with live predictions and connected account info."""
    active_account = UserBrokerAccount.objects.filter(
        user=request.user, 
        broker='DERIV', 
        is_active=True
    ).first()

    app_id = getattr(settings, 'DERIV_APP_ID', '1089')
    deriv_oauth_url = f"https://oauth.deriv.com/oauth2/authorize?app_id={app_id}"

    context = {
        'active_account': active_account,
        'deriv_oauth_url': deriv_oauth_url,
        'app_id': app_id,
    }
    return render(request, 'store/ai_prediction_models.html', context)


@login_required
def dashboard_view(request):
    return render(request, 'store/dashboard.html')


@login_required
def market_overview_view(request):
    return render(request, 'store/market_overview.html')


def market_dashboard(request):
    assets = Asset.objects.all()
    first_asset = assets.first()
    context = {
        'instruments': assets,
        'first_asset': first_asset,
    }
    return render(request, 'store/home.html', context)


def ai_analysis_api(request, asset_id):
    asset = get_object_or_404(Asset, id=asset_id)
    return JsonResponse({'status': 'success', 'data': {'symbol': asset.symbol, 'price': asset.price}})


@login_required
def open_trade(request):
    if request.method == 'POST':
        asset_id = request.POST.get('asset_id')
        direction = request.POST.get('direction', 'BUY').upper()
        stake = request.POST.get('stake', 10.00)

        asset = get_object_or_404(Asset, id=asset_id)

        Trade.objects.create(
            user=request.user,
            asset=asset,
            direction=direction,
            stake=float(stake),
            entry_price=asset.price,
            status='OPEN'
        )
        messages.success(request, f"Trade opened: {direction} on {asset.symbol}")
        return redirect('my_trades')

    return redirect('home')


# Auth Views
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("ai_prediction_models")
        messages.error(request, "Invalid credentials")
    return render(request, "store/login.html")


def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = User.objects.create_user(username=username, password=password)
        login(request, user)
        return redirect("ai_prediction_models")
    return render(request, "store/signup.html")


@login_required
def connect_broker(request):
    """Handles manual connection of Deriv / Pepperstone broker credentials."""
    if request.method == 'POST':
        broker = request.POST.get('broker', 'DERIV')
        account_number = request.POST.get('account_number')
        server_or_token = request.POST.get('server_or_token')

        if account_number:
            # Set previous accounts to inactive for this broker
            UserBrokerAccount.objects.filter(user=request.user, broker=broker).update(is_active=False)

            # Create or update the broker account
            UserBrokerAccount.objects.create(
                user=request.user,
                broker=broker,
                account_number=account_number,
                api_token=server_or_token,
                server_name='Deriv-Server' if broker == 'DERIV' else server_or_token,
                is_active=True
            )
            messages.success(request, f"Successfully connected {broker} account ({account_number})!")
        else:
            messages.error(request, "Please enter a valid account login / ID.")

    return redirect('ai_prediction_models')


def logout_view(request):
    logout(request)
    return redirect("login")


# Additional Page Placeholders
def live_signals(request): return render(request, 'store/live-signals.html')
def ai_signal_generator(request): return render(request, 'store/ai-signal-generator.html')
def market_overview(request): return render(request, 'store/market-overview.html')
def ai_market_summary(request): return render(request, 'store/ai-market-summary.html')
def ai_risk_analyzer(request): return render(request, 'store/ai-risk-analyzer.html')
def ai_trade_journal(request): return render(request, 'store/ai-trade-journal.html')
def ai_strategy_builder(request): return render(request, 'store/ai-strategy-builder.html')
def forex_heatmap(request): return render(request, 'store/forex-heatmap.html')
def crypto_heatmap(request): return render(request, 'store/crypto-heatmap.html')
def trend_scanner(request): return render(request, 'store/trend-scanner.html')
def pattern_detection(request): return render(request, 'store/pattern-detection.html')
def volatility_index(request): return render(request, 'store/volatility-index.html')
def economic_calendar(request): return render(request, 'store/economic-calendar.html')
def news_sentiment(request): return render(request, 'store/news-sentiment.html')
def correlation_matrix(request): return render(request, 'store/correlation-matrix.html')
def forex_analytics(request): return render(request, 'store/forex-analytics.html')
def crypto_analytics(request): return render(request, 'store/crypto-analytics.html')
def top_gainers_losers(request): return render(request, 'store/top-gainers-losers.html')
def market_sentiment(request): return render(request, 'store/market-sentiment.html')
def liquidity_zones(request): return render(request, 'store/liquidity-zones.html')
def price_action_monitor(request): return render(request, 'store/price-action-monitor.html')
def user_trades(request): return render(request, 'store/portfolio.html')
def open_positions(request): return render(request, 'store/open-positions.html')
def trade_history(request): return render(request, 'store/trade-history.html')
def performance_analytics(request): return render(request, 'store/performance-analytics.html')
def risk_metrics(request): return render(request, 'store/risk-metrics.html')
def pl_overview(request): return render(request, 'store/pl-overview.html')
def forex_pairs(request): return render(request, 'store/forex-pairs.html')
def crypto_pairs(request): return render(request, 'store/crypto-pairs.html')
def custom_alerts(request): return render(request, 'store/custom-alerts.html')
def saved_signals(request): return render(request, 'store/saved-signals.html')
def bot_center(request): return render(request, 'store/bot-center.html')
def auto_signal_forwarder(request): return render(request, 'store/auto-signal-forwarder.html')
def webhook_automations(request): return render(request, 'store/webhook-automations.html')
def api_integrations(request): return render(request, 'store/api-integrations.html')
def profile_security(request): return render(request, 'store/profile-security.html')
def notification_settings(request): return render(request, 'store/notification-settings.html')
def connected_exchanges(request): return render(request, 'store/connected-exchanges.html')
def subscription_billing(request): return render(request, 'store/subscription-billing.html')
def help_center(request): return render(request, 'store/help-center.html')
def run_sentiment_analysis_view(request): return redirect('ai_prediction_models')