# store/views.py (Top of your file)
import json
import random
import asyncio
from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.db.models import Avg
from django.dispatch import receiver
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
# --- MPESA IMPORTS ---
# Requires: pip install django-daraja
from django_daraja.mpesa.core import MpesaClient
from .models import (
    PaymentRequest, 
    Asset, 
    Trade, 
    UserBrokerAccount, 
    SentimentSignal, 
    NewsArticle, 
    Transaction, 
    Account, 
    UserProfile,
    Notification, 
    Webhook, 
    MpesaPayment, 
    SiteSettings,
    WebhookEndpoint
)

# --- EXISTING VIEWS (Authentication & Dashboards) ---

def login_view(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
        if user:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid credentials")
    return render(request, "store/login.html")

def signup_view(request):
    if request.method == "POST":
        user = User.objects.create_user(username=request.POST.get("username"), password=request.POST.get("password"))
        # Auto-login after signup
        login(request, user)
        # Redirect to connect broker
        return redirect("ai_prediction_models")
    return render(request, "store/signup.html")

def logout_view(request):
    logout(request)
    return redirect("login")

@login_required
def dashboard_view(request):
    notifications = Notification.objects.filter(user=request.user)[:5]

    # Site wallet balance — this, not any Deriv account, is what trades settle against.
    account, _ = Account.objects.get_or_create(user=request.user)

    site_settings = SiteSettings.load()

    return render(request, 'store/dashboard.html', {
        'notifications': notifications,
        'balance': account.balance,
        'default_trade_amount': site_settings.default_trade_amount,
        'min_trade_amount': site_settings.min_trade_amount,
        'max_trade_amount': site_settings.max_trade_amount,
        'trading_enabled': site_settings.trading_enabled,
    })


@login_required
def ai_prediction_models(request):
    """
    Deriv connection page. READ-ONLY: lets a trader link a Deriv account
    purely to display its (demo) balance for reference. No trade is ever
    placed against this account — all trading happens against the site
    wallet balance shown on the dashboard.
    """
    active_account = UserBrokerAccount.objects.filter(user=request.user, broker='DERIV', is_active=True).first()
    app_id = getattr(settings, 'DERIV_APP_ID', '33XN84FbZfx1ZO1xDyUzH')

    deriv_balance = None
    if active_account and active_account.api_token:
        try:
            deriv_service = DerivService()
            deriv_balance = asyncio.run(deriv_service.get_account_info(
                token=active_account.api_token,
                account_number=active_account.account_number
            ))
        except Exception:
            deriv_balance = None

    context = {
        'active_account': active_account,
        'deriv_oauth_url': f"https://oauth.deriv.com/oauth2/authorize?app_id={app_id}",
        'app_id': app_id,
        'deriv_balance': deriv_balance,  # view-only — never used to fund a trade
    }
    return render(request, 'store/ai_prediction_models.html', context)

@login_required
def connect_deriv(request):
    app_id = getattr(settings, 'DERIV_APP_ID', '33XN84FbZfx1ZO1xDyUzH')
    deriv_oauth_url = f"https://oauth.deriv.com/oauth2/authorize?app_id={app_id}"
    return redirect(deriv_oauth_url)

@login_required
def deriv_callback(request):
    UserBrokerAccount.objects.filter(user=request.user, broker='DERIV').update(is_active=False)
    saved_accounts_count = 0
    index = 1
    while True:
        acct_param, token_param, cur_param = f'acct{index}', f'token{index}', f'cur{index}'
        account_number = request.GET.get(acct_param)
        api_token = request.GET.get(token_param)
        currency = request.GET.get(cur_param, 'USD')
        if not account_number or not api_token: break
        is_demo_account = account_number.startswith('VRTC')
        UserBrokerAccount.objects.update_or_create(
            user=request.user, broker='DERIV', account_number=account_number,
            defaults={'api_token': api_token, 'currency': currency, 'is_demo': is_demo_account, 'is_active': (index == 1)}
        )
        saved_accounts_count += 1
        index += 1
    if saved_accounts_count > 0: messages.success(request, f"Successfully connected {saved_accounts_count} Deriv account(s)!")
    else: messages.error(request, "Failed to connect Deriv account.")
    return redirect('ai_prediction_models')

@login_required
def connect_broker(request):
    if request.method == 'POST':
        broker = request.POST.get('broker', 'DERIV')
        account_number = request.POST.get('account_number')
        if account_number:
            UserBrokerAccount.objects.filter(user=request.user, broker=broker).update(is_active=False)
            UserBrokerAccount.objects.create(user=request.user, broker=broker, account_number=account_number, api_token=request.POST.get('server_or_token'), is_active=True)
            messages.success(request, f"Connected {broker}!")
    return redirect('ai_prediction_models')


# --- FINANCIAL & PAYMENT VIEWS ---
@login_required
def funding_deposit(request):
    return render(request, 'store/payment.html')

@login_required
def funded_view(request):
    return render(request, 'store/funded.html', {})


# --- INTEGRATED DEPOSIT VIEW (Handles M-Pesa STK Push) ---

# store/views.py
# store/views.py
def format_mpesa_number(phone_number):
    phone = str(phone_number).strip().replace(" ", "").replace("+", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif not phone.startswith("254"):
        phone = "254" + phone
    return phone

def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json'


@login_required
def subscription_billing(request):
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        tier = request.POST.get('tier', 'pro')
        payment_method = request.POST.get('payment_method', 'mpesa')
        raw_phone = request.POST.get('phone_number')

        tier_prices = {
            'pro': Decimal('49.00'),
            'vip': Decimal('199.00')
        }
        amount_usd = tier_prices.get(tier, Decimal('49.00'))
        amount_kes = int(amount_usd * Decimal('130'))

        if payment_method.lower() in ('mpesa', 'm-pesa'):
            if not raw_phone:
                messages.error(request, 'M-Pesa phone number is required for STK push.')
                return redirect('subscription_billing')

            formatted_phone = format_mpesa_number(raw_phone)

            try:
                client = MpesaClient()
                response = client.stk_push(
                    phone_number=formatted_phone,
                    amount=amount_kes,
                    account_reference=f"SUB-{request.user.id}",
                    transaction_desc=f"Subscription {tier.upper()}",
                    callback_url=settings.MPESA_CALLBACK_URL
                )

                if response.response_code == '0':
                    # Fixed: Store tier inside transaction_type since PaymentRequest lacks a 'tier' field
                    payment_req = PaymentRequest.objects.create(
                        user=request.user,
                        amount=amount_usd,
                        transaction_type=f'SUB_{tier.upper()}',
                        payment_method='M-Pesa',
                        status='PROCESSING'
                    )
                    MpesaPayment.objects.create(
                        payment_request=payment_req,
                        merchant_request_id=response.merchant_request_id,
                        checkout_request_id=response.checkout_request_id,
                        phone_number=formatted_phone,
                        amount=amount_usd
                    )
                    messages.success(request, 'STK Push sent! Please check your phone and enter your M-Pesa PIN.')
                else:
                    err_msg = getattr(response, 'response_description', 'Failed to initiate M-Pesa STK push.')
                    messages.error(request, err_msg)
            except Exception as e:
                messages.error(request, f"M-Pesa error: {str(e)}")

        elif payment_method.lower() == 'balance':
            account, _ = Account.objects.get_or_create(user=request.user)
            if account.balance >= amount_usd:
                account.balance -= amount_usd
                account.save()

                user_profile.subscription_tier = tier
                user_profile.save()

                Transaction.objects.create(
                    user=request.user,
                    amount=amount_usd,
                    transaction_type='DEPOSIT',
                    details=f"Unlocked {tier.upper()} tier via account balance"
                )
                messages.success(request, f"Successfully subscribed to {tier.upper()}!")
            else:
                messages.error(request, 'Insufficient account balance.')

        # Redirect user to payment status page to track progress
        return redirect('payment_status')

    return render(request, 'store/subscription-billing.html', {'user_profile': user_profile})


@csrf_exempt
def mpesa_callback(request):
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)

    try:
        body = json.loads(request.body.decode('utf-8'))
        stk_callback = body.get('Body', {}).get('stkCallback', {})
        checkout_request_id = stk_callback.get('CheckoutRequestID')
        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc')

        with transaction.atomic():
            payment_pay = MpesaPayment.objects.select_for_update().filter(
                checkout_request_id=checkout_request_id
            ).first()

            if not payment_pay:
                return JsonResponse({"ResultCode": 1, "ResultDesc": "Record not found"}, status=404)

            payment_req = payment_pay.payment_request
            payment_pay.result_code = result_code
            payment_pay.result_desc = result_desc

            if result_code == 0:
                metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
                receipt_number = ''
                for item in metadata:
                    if item.get('Name') == 'MpesaReceiptNumber':
                        receipt_number = str(item.get('Value'))

                payment_pay.mpesa_receipt_number = receipt_number
                payment_pay.save()

                if payment_req:
                    payment_req.status = 'APPROVED'
                    payment_req.processed = True
                    payment_req.save()

                    # Handle subscription upgrade if transaction_type indicates a subscription
                    if payment_req.transaction_type.startswith('SUB_'):
                        tier_name = payment_req.transaction_type.split('_')[1].lower()
                        profile, _ = UserProfile.objects.get_or_create(user=payment_req.user)
                        profile.subscription_tier = tier_name
                        profile.save()

                    Transaction.objects.create(
                        user=payment_req.user,
                        amount=payment_req.amount,
                        transaction_type='DEPOSIT',
                        details=f"M-Pesa Payment Success - Receipt: {receipt_number}"
                    )
            else:
                payment_pay.save()
                if payment_req:
                    payment_req.status = 'REJECTED'
                    payment_req.save()

        return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
    except Exception as e:
        return JsonResponse({"ResultCode": 1, "ResultDesc": str(e)}, status=500)


@login_required
def check_payment_status(request, checkout_id):
    """Polls the status of an ongoing M-Pesa transaction."""
    payment = get_object_or_404(MpesaPayment, checkout_request_id=checkout_id)
    pref_req = payment.payment_request

    status = pref_req.status if pref_req else 'PROCESSING'
    
    if status in ['APPROVED', 'COMPLETED']:
        return JsonResponse({'status': 'completed', 'message': 'Payment successful! Unlocking subscription...'})
    elif status in ['REJECTED', 'FAILED']:
        return JsonResponse({'status': 'failed', 'message': 'Not paid: Payment was cancelled or failed.'})
    else:
        return JsonResponse({'status': 'pending', 'message': 'Waiting for M-Pesa PIN entry...'})




def _deposit_response(request, success, message, redirect_to='funding_deposit'):
    """
    Returns JSON for the AJAX deposit form (deposit.html) and a normal
    redirect-with-message for the standard modal form (payment.html).
    """
    if _is_ajax(request):
        return JsonResponse({'success': success, 'error': None if success else message,
                              'message': message if success else None})
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect(redirect_to)


@login_required
def request_deposit(request):
    if request.method != 'POST':
        return redirect('funding_deposit')

    # Support both a JSON body (deposit.html's fetch()) and a normal
    # form-encoded POST (payment.html's modal form).
    if request.content_type == 'application/json':
        try:
            body = json.loads(request.body.decode('utf-8'))
        except (ValueError, json.JSONDecodeError):
            body = {}
    else:
        body = request.POST

    amount_str = body.get('amount')
    method_val = body.get('method', 'M-Pesa')
    # Accept either field name so both forms work against this one endpoint.
    raw_phone = body.get('phone_number') or body.get('phone')

    # 1. Validate Amount using Decimal
    try:
        amount = Decimal(str(amount_str))
        if amount <= 0:
            return _deposit_response(request, False, "Amount must be greater than 0.")
    except (InvalidOperation, ValueError, TypeError):
        return _deposit_response(request, False, "Invalid deposit amount.")

    # 2. Process M-Pesa STK Push
    if method_val.upper() in ('MPESA', 'M-PESA'):
        if not raw_phone:
            return _deposit_response(request, False, "Phone number is required for M-Pesa deposits.")

        formatted_phone = format_mpesa_number(raw_phone)

        try:
            client = MpesaClient()
            response = client.stk_push(
                phone_number=formatted_phone,
                amount=int(amount),
                account_reference=f"DEP-{request.user.id}",
                transaction_desc=f"Deposit for {request.user.username}",
                callback_url=settings.MPESA_CALLBACK_URL
            )

            if response.response_code == '0':
                payment_req = PaymentRequest.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type='DEPOSIT',
                    payment_method='M-Pesa',
                    status='PROCESSING'
                )
                MpesaPayment.objects.create(
                    payment_request=payment_req,
                    merchant_request_id=response.merchant_request_id,
                    checkout_request_id=response.checkout_request_id
                )
                return _deposit_response(request, True, f"STK Push sent to {formatted_phone}. Please check your phone.")
            else:
                return _deposit_response(request, False, f"M-Pesa error: {getattr(response, 'response_description', 'Unknown error')}")
        except Exception as e:
            return _deposit_response(request, False, f"Payment initiation failed: {str(e)}")
    else:
        # 3. Standard Manual Deposit Flow
        PaymentRequest.objects.create(
            user=request.user,
            amount=amount,
            transaction_type='DEPOSIT',
            payment_method=method_val,
            status='PENDING',
            processed=False
        )
        return _deposit_response(request, True, "Deposit request submitted. Awaiting admin approval.", redirect_to='dashboard')




from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from django.db.models import Avg
from decimal import Decimal, InvalidOperation
import urllib.parse
from django.dispatch import receiver
from .models import PaymentRequest, Asset, Trade, UserBrokerAccount, SentimentSignal, NewsArticle, Transaction, Account, Notification, Webhook
from django.db import transaction

def request_withdrawal(request):
    """
    Consolidated withdrawal view that uses Decimal to prevent TypeError.
    """
    if request.method == 'POST':
        amount_str = request.POST.get('amount')
        
        try:
            # 1. Convert input directly to Decimal
            amount = Decimal(amount_str)
            
            # 2. Get user account
            user_account, created = Account.objects.get_or_create(user=request.user)
            
            # 3. Check balance (both are now Decimals)
            if user_account.balance >= amount:
                # Subtract balance safely
                user_account.balance -= amount
                user_account.save()
                
                # Log the transaction
                Transaction.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type='WITHDRAWAL',
                    details=request.POST.get('details', 'Withdrawal Request')
                )
                messages.success(request, "Withdrawal successful.")
            else:
                messages.error(request, "Insufficient funds.")
                
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, "Invalid withdrawal amount.")
            
    return redirect('dashboard')

@login_required
def trade_view(request):
    return render(request, 'store/trade.html')

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import PaymentRequest

@staff_member_required
def admin_payment_dashboard(request):
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        
        payment_req = get_object_or_404(PaymentRequest, id=request_id)
        
        if action == 'APPROVE':
            payment_req.status = 'APPROVED'
        else:
            payment_req.status = 'REJECTED'
            
        payment_req.save() # This triggers your post_save signal
        return redirect('admin_payment_dashboard')

    # Get only pending requests
    pending_requests = PaymentRequest.objects.filter(status='PENDING')
    return render(request, 'store/admin_approvals.html', {'requests': pending_requests})


def news_sentiment(request):
    articles = NewsArticle.objects.all().order_by('-published')[:10]
    stats = NewsArticle.objects.aggregate(avg_polarity=Avg('polarity'))
    avg_polarity = stats['avg_polarity'] or 0
    overall_sentiment = "Bullish" if avg_polarity > 0.1 else "Bearish" if avg_polarity < -0.1 else "Neutral"
    context = {'news_list': articles, 'overall_sentiment': overall_sentiment, 'avg_polarity': round(avg_polarity, 2)}
    return render(request, 'store/news_sentiment.html', context)


@login_required
def market_overview_view(request):
    return render(request, 'store/market_overview.html')

def market_dashboard(request):
    assets = Asset.objects.all()
    context = {'instruments': assets, 'first_asset': assets.first()}
    return render(request, 'store/home.html', context)

def ai_analysis_api(request, asset_id):
    asset = get_object_or_404(Asset, id=asset_id)
    return JsonResponse({'status': 'success', 'data': {'symbol': asset.symbol, 'price': asset.price}})

@login_required
def open_trade(request):
    if request.method == 'POST':
        asset = get_object_or_404(Asset, id=request.POST.get('asset_id'))
        Trade.objects.create(
            user=request.user, asset=asset, direction=request.POST.get('direction', 'BUY').upper(),
            stake=Decimal(request.POST.get('stake', 10)), entry_price=asset.price, status='OPEN'
        )
        messages.success(request, "Trade opened")
        return redirect('my_trades')
    return redirect('home')


@login_required
@csrf_exempt
def execute_trade(request):
    """Evaluates real-time digit trades, updates account balance, and logs Trade history."""
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)
    
    try:
        data = json.loads(request.body)
        symbol = data.get('symbol', 'R_10')
        contract_type = data.get('contract_type', 'DIGITMATCH') 
        amount = Decimal(str(data.get('amount', '10'))) # Safely cast to Decimal
        barrier = data.get('barrier')
        
        with transaction.atomic():
            account = Account.objects.select_for_update().get(user=request.user)
            
            if account.balance < amount:
                return JsonResponse({"success": False, "error": "Insufficient balance in your account."}, status=400)
            
            # 1. Deduct stake safely from site wallet balance
            account.balance -= amount
            account.save()
            
            # Get or create Asset reference for the Trade model foreign key
            asset_obj, _ = Asset.objects.get_or_create(
                symbol=symbol,
                defaults={'name': symbol, 'asset_type': 'synthetic', 'price': Decimal('1000.00')}
            )
            
            # 2. Real-time tick evaluation outcome (0 to 9)
            final_digit = random.randint(0, 9)
            won = False
            payout = Decimal('0.0')
            
            # 3. Evaluate rules & multipliers using Decimals
            if contract_type == 'DIGITMATCH':
                won = (final_digit == int(barrier))
                payout = amount * Decimal('9.5') if won else Decimal('0.0')
            elif contract_type == 'DIGITDIFF':
                won = (final_digit != int(barrier))
                payout = amount * Decimal('1.12') if won else Decimal('0.0')
            elif contract_type == 'DIGITEVEN':
                won = (final_digit % 2 == 0)
                payout = amount * Decimal('1.98') if won else Decimal('0.0')
            elif contract_type == 'DIGITODD':
                won = (final_digit % 2 != 0)
                payout = amount * Decimal('1.98') if won else Decimal('0.0')
            elif contract_type == 'DIGITOVER':
                won = (final_digit > int(barrier))
                multipliers = {0: Decimal('1.05'), 1: Decimal('1.15'), 2: Decimal('1.35'), 3: Decimal('1.65'), 4: Decimal('2.15'), 5: Decimal('3.15'), 6: Decimal('5.35'), 7: Decimal('10.5'), 8: Decimal('32.5')}
                payout = amount * multipliers.get(int(barrier), Decimal('2.0')) if won else Decimal('0.0')
            elif contract_type == 'DIGITUNDER':
                won = (final_digit < int(barrier))
                multipliers = {1: Decimal('32.5'), 2: Decimal('10.5'), 3: Decimal('5.35'), 4: Decimal('3.15'), 5: Decimal('2.15'), 6: Decimal('1.65'), 7: Decimal('1.35'), 8: Decimal('1.15')}
                payout = amount * multipliers.get(int(barrier), Decimal('2.0')) if won else Decimal('0.0')

            if won:
                account.balance += payout
                account.save()
                
            # 4. Save Trade record so it appears in trades_history.html
            Trade.objects.create(
                user=request.user,
                asset=asset_obj,
                direction=contract_type,
                stake=amount,
                entry_price=asset_obj.price,
                target_digit=int(barrier) if barrier is not None else None,
                status='WON' if won else 'LOST',
                payout=payout if won else Decimal('0.00')
            )
            
            # 5. Optional: Safe Transaction logging (matching fields present in models.py)
            Transaction.objects.create(
                user=request.user,
                amount=payout if won else amount,
                transaction_type='DEPOSIT' if won else 'WITHDRAWAL', # Keep valid choices if enforced, or use details
                details=f"Trade {contract_type} | Final Digit: {final_digit} | Result: {'WIN' if won else 'LOSS'}"
            )
            
            return JsonResponse({
                "success": True,
                "won": won,
                "final_digit": final_digit,
                "payout": float(payout),
                "new_balance": float(round(account.balance, 2))
            })
            
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def trade_history(request):
    """Retrieves all completed trades for the user to display in trade history."""
    trades = Trade.objects.filter(user=request.user).exclude(status='OPEN').order_by('-date_opened')
    return render(request, 'store/trades_history.html', {'trades': trades})

@login_required
def digits_trading(request):
    return render(request, 'store/digits_trading.html')

# Simplified place holder views
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
def correlation_matrix(request): return render(request, 'store/correlation-matrix.html')
def forex_analytics(request): return render(request, 'store/forex-analytics.html')
def crypto_analytics(request): return render(request, 'store/crypto-analytics.html')
def top_gainers_losers(request): return render(request, 'store/top-gainers-losers.html')
def market_sentiment(request): return render(request, 'store/market-sentiment.html')
def liquidity_zones(request): return render(request, 'store/liquidity-zones.html')
def price_action_monitor(request): return render(request, 'store/price-action-monitor.html')
def user_trades(request): return render(request, 'store/portfolio.html')
def open_positions(request): return render(request, 'store/open-positions.html')
def performance_analytics(request): return render(request, 'store/performance-analytics.html')
def risk_metrics(request): return render(request, 'store/risk-metrics.html')
def pl_overview(request): return render(request, 'store/pl-overview.html')
def forex_pairs(request): return render(request, 'store/forex-pairs.html')
def crypto_pairs(request): return render(request, 'store/crypto-pairs.html')
def custom_alerts(request): return render(request, 'store/custom-alerts.html')
def saved_signals(request): return render(request, 'store/saved-signals.html')
def bot_center(request): return render(request, 'store/bot-center.html')
def auto_signal_forwarder(request): return render(request, 'store/auto-signal-forwarder.html')
def api_integrations(request): return render(request, 'store/api-integrations.html')
def profile_security(request): return render(request, 'store/profile-security.html')
def notification_settings(request): return render(request, 'store/notification-settings.html')
def connected_exchanges(request): return render(request, 'store/connected-exchanges.html')
def help_center(request): return render(request, 'store/help-center.html')
def run_sentiment_analysis_view(request): return redirect('ai_prediction_models')

from django.shortcuts import render
from .models import Trade # Import your actual Trade model

@login_required
def trade_history(request):
    # Retrieve only WON, LOST, or CANCELLED trades
    trades = Trade.objects.filter(user=request.user).exclude(status='OPEN').order_by('-date_opened')
    return render(request, 'store/trades_history.html', {'trades': trades})

    from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def admin_deposit_approval_view(request):
    # This is a placeholder for now
    return render(request, 'admin/deposit_approval.html')

    from .models import Transaction

def check_notifications(request):
    # Now that we added 'status' to the model, this query will work
  # Change this:
# new_transactions = Transaction.objects.filter(status='...', is_notified=False)

# To this:
    new_transactions = Transaction.objects.filter(is_notified=False)
    
    notifications = []
    for tx in new_transactions:
        notifications.append({
            'title': f'{tx.transaction_type.capitalize()} Accepted',
            'message': f'Your {tx.transaction_type} of ${tx.amount} is complete.',
            'link': '/funded/'
        })
        # Mark as notified so it doesn't appear again
        tx.is_notified = True
        tx.save()
        
    return JsonResponse({'new_notifications': notifications})

@login_required
@transaction.atomic
def close_trade(request, trade_id, status, final_payout):
    trade = get_object_or_404(Trade, id=trade_id, user=request.user)
    
    if trade.status != 'OPEN':
        messages.error(request, "Trade is already closed.")
        return redirect('trade_history')

    # Update trade status
    trade.status = status
    trade.payout = Decimal(str(final_payout))
    trade.save()

    # Credit the balance if won (or refund if needed)
    if status == 'WON':
        account = Account.objects.get(user=request.user)
        account.balance += trade.payout
        account.save()
        messages.success(request, f"Trade closed! Profit: ${trade.payout}")
    else:
        messages.info(request, "Trade closed.")
        
    return redirect('trade_history')


# views.py
@login_required
def profile(request):
    # Fetch the last 5 notifications for the user
    user_notifications = Notification.objects.filter(user=request.user)[:5]
    return render(request, 'store/profile.html', {
        'notifications': user_notifications
    })


@login_required
@transaction.atomic
def process_transaction(request):
    if request.method == 'POST':
        # 1. Parse input
        try:
            amount = Decimal(request.POST.get('amount'))
            t_type = request.POST.get('type')  # Expecting 'DEPOSIT' or 'WITHDRAWAL'
        except (ValueError, TypeError):
            messages.error(request, "Invalid transaction amount.")
            return redirect('dashboard')

        account = Account.objects.get(user=request.user)

        # 2. Logic for Balance Adjustment
        if t_type == 'WITHDRAWAL':
            if account.balance < amount:
                messages.error(request, "Insufficient funds for withdrawal.")
                return redirect('dashboard')
            account.balance -= amount
        else:
            # Assume DEPOSIT
            account.balance += amount
        
        # Save account balance
        account.save()

        # 3. Create Transaction Log
        txn = Transaction.objects.create(
            user=request.user,
            amount=amount,
            transaction_type=t_type,
            status='APPROVED'
        )

        # 4. Create Notification
        Notification.objects.create(
            user=request.user,
            title="Transaction Successful",
            message=f"Your {t_type.lower()} of ${amount} was successful."
        )

        messages.success(request, f"{t_type.capitalize()} of ${amount} completed.")
        return redirect('dashboard')
    
    # If not POST, redirect to your transaction form page
    return render(request, 'store/transaction.html')

@login_required
def webhook_automations(request):
    webhooks = Webhook.objects.filter(user=request.user)
    # Calculate aggregate stats for the top cards
    context = {
        'webhooks': webhooks,
        'total_webhooks': webhooks.count(),
        'active_count': webhooks.filter(is_active=True).count()
    }
    return render(request, 'store/webhooks.html', context)


# store/views.py
from django.conf import settings
from .models import WebhookLog

@csrf_exempt
def handle_incoming_webhook(request, source_name='Generic'):
    """
    General-purpose webhook automation endpoint.
    Verifies token, logs payload, and triggers automated actions.
    """
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)

    # 1. Security Check: Validate Secret Token from Headers
    # Expected header format: 'X-Webhook-Secret': 'your-secure-token'
    client_token = request.headers.get('X-Webhook-Secret')
    expected_token = getattr(settings, 'WEBHOOK_SECRET_KEY', 'default-secret-token')
    
    if client_token != expected_token:
        return JsonResponse({"status": "error", "message": "Unauthorized webhook token"}, status=403)

    # 2. Extract Request Headers and Body
    headers_dict = {k: v for k, v in request.headers.items()}
    raw_body = request.body.decode('utf-8')

    # 3. Log the Webhook immediately for audit tracking
    webhook_log = WebhookLog.objects.create(
        source=source_name,
        payload=raw_body,
        headers=json.dumps(headers_dict)
    )

    try:
        data = json.loads(raw_body)
        
        # 4. Automation Dispatcher Logic
        if source_name.lower() == 'tradingview':
            # Example automation: Parse candlestick pattern signal or price action alert
            ticker = data.get('ticker')
            action = data.get('action') # e.g., 'BUY', 'SELL'
            price = data.get('price')
            
            # TODO: Insert your automated trading logic here
            # e.g., execute_trade(ticker, action, price)
            
        elif source_name.lower() == 'custom_automation':
            # Handle other custom automated tasks
            event_type = data.get('event')
            # Handle event_type...

        # Mark log as successfully processed
        webhook_log.is_processed = True
        webhook_log.save()

        return JsonResponse({"status": "success", "message": "Webhook processed successfully"}, status=200)

    except Exception as e:
        # Catch and log any automation execution failures
        webhook_log.is_processed = False
        webhook_log.error_message = str(e)
        webhook_log.save()
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


# store/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import WebhookEndpoint

@login_required
def webhook_automations_view(request):
    # Fetch all webhook endpoints belonging to the logged-in user
    user_webhooks = WebhookEndpoint.objects.filter(user=request.user)
    
    # Calculate active webhooks count for the header badge
    active_count = user_webhooks.filter(is_active=True).count()
    
    # Compute dynamic stats data for the stats grid loop[cite: 6]
    total_requests = sum(w.requests_count for w in user_webhooks)
    avg_latency = int(sum(w.latency for w in user_webhooks) / user_webhooks.count()) if user_webhooks.exists() else 0
    avg_success = round(sum(w.success_rate for w in user_webhooks) / user_webhooks.count(), 1) if user_webhooks.exists() else 100.0

    stats_data = {
        'Total Endpoints': user_webhooks.count(),
        'Total Requests': total_requests,
        'Avg Success Rate': f"{avg_success}%",
        'Avg Latency': f"{avg_latency}ms"
    }

    context = {
        'active_count': active_count,
        'stats_data': stats_data,
        'webhooks': user_webhooks,
    }
    
    return render(request, 'store/webhook_automations.html', context)

@login_required
def toggle_webhook_status(request, webhook_id):
    """View to handle toggling the webhook active state via checkbox/switch."""
    webhook = get_object_or_404(WebhookEndpoint, id=webhook_id, user=request.user)
    webhook.is_active = not webhook.is_active
    webhook.save()
    return redirect('webhook_automations')


@login_required
def create_webhook(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        url = request.POST.get('url')
        webhook_type = request.POST.get('type', 'OUT') # Default to Outgoing
        
        if name and url:
            Webhook.objects.create(
                user=request.user,
                name=name,
                url=url,
                type=webhook_type,
                is_active=True,
                requests_count=0,
                success_rate=100.0,
                latency=0
            )
            messages.success(request, "Webhook endpoint created successfully.")
        else:
            messages.error(request, "Both Name and URL are required.")
            
    return redirect('webhook_automations')

@login_required
def payment_status_view(request):
    # Fetch deposits and withdrawals history
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    
    # Fetch pending/processed payment requests (like STK push requests)
    payment_requests = PaymentRequest.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'transactions': transactions,
        'payment_requests': payment_requests,
    }
    return render(request, 'store/payment_status.html', context)


@login_required
def bot_dashboard_view(request):
    """
    Renders the main bot.html template with current status and data.
    """
    # --- MOCK DATA FOR DISPLAY (Replace with real DB queries later) ---
    # In a real scenario, you would fetch this from UserProfile, 
    # SiteSettings, or an active bot process.
    context = {
        'bot_status': 'stopped', # options: 'running', 'stopped', 'error'
        'current_pair': 'LTC/USDT',
        'account_balance': 1250.45,
        'unrealized_pnl': -5.20,
        'pnl_pct': -0.41,
        'active_orders_count': 3,
        'next_buy_price': 92.50,
        # 'logs': core.bot_logger.get_logs() # Example of fetching real logs
        'logs': [
            {'timestamp': '10:00:01', 'message': 'System initialized in demo mode.'},
            {'timestamp': '10:00:05', 'message': 'Waiting for market data...' },
        ]
    }
    return render(request, 'store/bot.html', context)

@login_required
def bot_control_view(request):
    """
    Handles POST requests from the buttons in bot.html.
    Redirects back to the dashboard with a success message.
    """
    if request.method == 'POST':
        action = request.POST.get('action')

        # --- INTEGRATION WITH YOUR CORE.PY LOGIC ---
        if action == 'start':
            # Example: core.start_bot_thread(user=request.user)
            messages.success(request, "AI Trading Engine started successfully.")
            
        elif action == 'stop':
            # Example: core.stop_bot_thread(user=request.user)
            messages.info(request, "AI Trading Engine received stop signal.")
            
        elif action == 'emergency_stop':
            # Example: core.execute_emergency_sell(user=request.user)
            messages.warning(request, "EMERGENCY SELL EXECUTED. All positions closed.")

        # Add a delay here if needed to allow the bot state to change before reload
        # time.sleep(1) 
        
        return redirect_url('bot_dashboard')
    
    # If someone tries to GET this URL directly, send them to the dashboard
    return redirect(redirect_url)  # ✅ Calls Django's redirect function properly

    from django.shortcuts import render, redirect
from .forms import CreateBotForm

from .models import BotLog
from .forms import CreateBotForm

def bot_dashboard_view(request):
    form = CreateBotForm()
    
    # Fetch the latest 50 logs for the terminal window
    logs = BotLog.objects.all()[:50]
    
    context = {
        'form': form,
        'logs': logs,
        'bot_status': 'running', # Or 'stopped' based on your state logic
        'account_balance': 1000.00,
        'unrealized_pnl': 15.50,
        'pnl_pct': 1.55,
        'current_pair': 'R_100',
    }
    return render(request, 'store/bot.html', context)

def create_bot_view(request):
    """Handles the form submission from the modal to initialize a new bot."""
    if request.method == 'POST':
        form = CreateBotForm(request.POST)
        if form.is_valid():
            bot_name = form.cleaned_data['bot_name']
            strategy = form.cleaned_data['strategy']
            trading_pair = form.cleaned_data['trading_pair']
            stake_amount = form.cleaned_data['stake_amount']
            
            # TODO: Save the bot instance to your database model here
            # e.g., BotModel.objects.create(user=request.user, name=bot_name, ...)
            
            return redirect('bot')  # Redirects back to the bot dashboard page
            
    return redirect('bot')

from .models import BotLog

def log_bot_event(message, level='INFO'):
    """Helper to record bot events into the database."""
    BotLog.objects.create(message=message, level=level)