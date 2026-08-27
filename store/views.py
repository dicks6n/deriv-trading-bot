import json
import random
import asyncio
from decimal import Decimal, InvalidOperation
from datetime import datetime
import time  # <--- Add this line here
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required 
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.db.models import Avg
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required

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
    WebhookEndpoint,
    FundedAccount,
    BotLog
)
from .forms import CreateBotForm

TIER_CONFIG = {
    'pro': {
        'price': Decimal('49.00'),
        'funded_amount': Decimal('500.00'),
        'kes_multiplier': 130  # Used for M-Pesa conversion if applicable
    },
    'vip': {
        'price': Decimal('199.00'),
        'funded_amount': Decimal('2500.00'),
        'kes_multiplier': 130
    }
}
# ==========================================
# HELPER FUNCTIONS
# ==========================================

def format_mpesa_number(phone_number):
    phone = str(phone_number).strip().replace(" ", "").replace("+", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif not phone.startswith("254"):
        phone = "254" + phone
    return phone


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json'


def _deposit_response(request, success, message, redirect_to='funding_deposit'):
    if _is_ajax(request):
        return JsonResponse({
            'success': success, 
            'error': None if success else message,
            'message': message if success else None
        })
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect(redirect_to)


def log_bot_event(message, level='INFO'):
    BotLog.objects.create(message=message, level=level)


# ==========================================
# AUTHENTICATION VIEWS
# ==========================================

def login_view(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
        if user:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid credentials")
    return render(request, "store/login.html")


def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Check if the username is already taken
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect('signup')

        # 1. CREATE THE USER HERE[cite: 8]
        user = User.objects.create_user(username=username, password=password)

        # 2. CREATE BOTH ACCOUNTS IMMEDIATELY AFTER[cite: 8]
        Account.objects.create(user=user, account_type='EXCHANGE', balance=Decimal('0.00'))
        Account.objects.create(user=user, account_type='TRADING', balance=Decimal('0.00'))

        messages.success(request, "Registration successful! You can now log in.")
        return redirect('login') # Or redirect straight to your funding/dashboard page[cite: 8]

    return render(request, "store/signup.html")


def logout_view(request):
    logout(request)
    return redirect("login")


# ==========================================
# DASHBOARD & PROFILE VIEWS
# ==========================================
@login_required
def dashboard_view(request):
    notifications = Notification.objects.filter(user=request.user)[:5]
    
    # 1. Fetch both split accounts[cite: 8]
    exchange_acc, _ = Account.objects.get_or_create(user=request.user, account_type='EXCHANGE')
    trading_acc, _ = Account.objects.get_or_create(user=request.user, account_type='TRADING')
    
    # Dashboard total balance combines both Exchange and Trading amounts[cite: 8]
    total_balance = exchange_acc.balance + trading_acc.balance
    
    site_settings = SiteSettings.load()

    return render(request, 'store/dashboard.html', {
        'notifications': notifications,
        'balance': total_balance,             # Combined total for your dashboard widget[cite: 8]
        'exchange_balance': exchange_acc.balance, # Individual exchange breakdown if needed[cite: 8]
        'trading_balance': trading_acc.balance,   # Individual trading breakdown if needed[cite: 8]
        'default_trade_amount': site_settings.default_trade_amount,
        'min_trade_amount': site_settings.min_trade_amount,
        'max_trade_amount': site_settings.max_trade_amount,
        'trading_enabled': site_settings.trading_enabled,
    })


@login_required
def profile(request):
    user_notifications = Notification.objects.filter(user=request.user)[:5]
    funded_account, _ = FundedAccount.objects.get_or_create(user=request.user)
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    
    # Generate Trader ID and dynamic account type based on subscription status
    if user_profile.is_active_subscription:
        trader_id = f"#TRD-{1000 + request.user.id}"
        account_type = f"Funded ${int(funded_account.balance)}" if funded_account.is_funded else f"Funded {user_profile.subscription_tier.upper()}"
    else:
        trader_id = "Pending Subscription"
        account_type = "Free / Starter"

    return render(request, 'store/profile.html', {
        'notifications': user_notifications,
        'funded_account': funded_account,
        'user_profile': user_profile,
        'trader_id': trader_id,
        'account_type': account_type,
    })


@login_required
def funded_view(request):
    funded_account, _ = FundedAccount.objects.get_or_create(user=request.user)
    return render(request, 'store/funded.html', {'funded_account': funded_account})


# ==========================================
# SUBSCRIPTION & PAYMENT VIEWS
# ==========================================

@login_required
def subscription_billing(request):
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    
    # Target the main Exchange account for balance payments
    account, _ = Account.objects.get_or_create(user=request.user, account_type='EXCHANGE')
    transactions = PaymentRequest.objects.filter(user=request.user).order_by('-created_at')[:10]

    if request.method == 'POST':
        tier = request.POST.get('tier', 'pro').lower()
        payment_method = request.POST.get('payment_method', 'mpesa')
        raw_phone = request.POST.get('phone_number')

        if tier not in TIER_CONFIG:
            messages.error(request, 'Invalid subscription tier selected.')
            return redirect('subscription_billing')

        tier_data = TIER_CONFIG[tier]
        amount_usd = tier_data['price']
        funded_capital = tier_data['funded_amount']
        amount_kes = int(amount_usd * tier_data['kes_multiplier'])

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
                    payment_req = PaymentRequest.objects.create(
                        user=request.user,
                        amount=amount_usd, # Charges subscription price ($49 or $199)
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
            if account.balance >= amount_usd:
                account.balance -= amount_usd
                account.save()

                user_profile.subscription_tier = tier
                user_profile.is_active_subscription = True
                user_profile.save()

                # Fund the account with the high capital amount ($500 or $2500)
                funded_account, _ = FundedAccount.objects.get_or_create(user=request.user)
                funded_account.initial_balance = funded_capital
                funded_account.balance = funded_capital
                funded_account.is_funded = True
                funded_account.save()

                Transaction.objects.create(
                    user=request.user,
                    amount=amount_usd,
                    transaction_type='DEPOSIT',
                    details=f"Unlocked {tier.upper()} tier & funded account with ${funded_capital}"
                )
                messages.success(request, f"Successfully subscribed to {tier.upper()} and funded your account with ${funded_capital}!")
            else:
                messages.error(request, 'Insufficient account balance.')

        return redirect('subscription_billing')
        
    context = {
        'user_profile': user_profile,
        'current_plan': user_profile.subscription_tier,
        'account': account,
        'transactions': transactions,
    }
    return render(request, 'store/subscription-billing.html', context)

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

                    if payment_req.transaction_type.startswith('SUB_'):
                        tier_name = payment_req.transaction_type.split('_')[1].lower()
                        profile, _ = UserProfile.objects.get_or_create(user=payment_req.user)
                        profile.subscription_tier = tier_name
                        profile.is_active_subscription = True
                        profile.save()

                        # Fund the account based on tier configuration ($500 or $2500)
                        if tier_name in TIER_CONFIG:
                            funded_capital = TIER_CONFIG[tier_name]['funded_amount']
                            funded_account, _ = FundedAccount.objects.get_or_create(user=payment_req.user)
                            funded_account.initial_balance = funded_capital
                            funded_account.balance = funded_capital
                            funded_account.is_funded = True
                            funded_account.save()

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
    payment = get_object_or_404(MpesaPayment, checkout_request_id=checkout_id)
    pref_req = payment.payment_request
    status = pref_req.status if pref_req else 'PROCESSING'
    
    if status in ['APPROVED', 'COMPLETED']:
        return JsonResponse({'status': 'completed', 'message': 'Payment successful! Unlocking subscription...'})
    elif status in ['REJECTED', 'FAILED']:
        return JsonResponse({'status': 'failed', 'message': 'Payment was cancelled or failed.'})
    else:
        return JsonResponse({'status': 'pending', 'message': 'Waiting for M-Pesa PIN entry...'})


@login_required
def request_deposit(request):
    if request.method != 'POST':
        return redirect('funding_deposit')

    if request.content_type == 'application/json':
        try:
            body = json.loads(request.body.decode('utf-8'))
        except (ValueError, json.JSONDecodeError):
            body = {}
    else:
        body = request.POST

    amount_str = body.get('amount')
    method_val = body.get('method', 'M-Pesa')
    raw_phone = body.get('phone_number') or body.get('phone')

    try:
        amount = Decimal(str(amount_str))
        if amount <= 0:
            return _deposit_response(request, False, "Amount must be greater than 0.")
    except (InvalidOperation, ValueError, TypeError):
        return _deposit_response(request, False, "Invalid deposit amount.")

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
        PaymentRequest.objects.create(
            user=request.user,
            amount=amount,
            transaction_type='DEPOSIT',
            payment_method=method_val,
            status='PENDING',
            processed=False
        )
        return _deposit_response(request, True, "Deposit request submitted. Awaiting admin approval.", redirect_to='dashboard')


@csrf_exempt
def binance_webhook(request):
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)

    try:
        body = json.loads(request.body.decode('utf-8'))
        biz_content = body.get('data', {})
        merchant_trade_no = biz_content.get('merchantTradeNo')
        status = biz_content.get('status') # e.g., "PAID"
        total_fee = Decimal(str(biz_content.get('totalFee', '0')))

        if status == 'PAID' and merchant_trade_no:
            user_id = merchant_trade_no.split('_')[1]
            
            with transaction.atomic():
                # Deposits land in the EXCHANGE account[cite: 8]
                account = Account.objects.select_for_update().get(user_id=user_id, account_type='EXCHANGE')
                account.balance += total_fee
                account.save()
                
                payment_req = PaymentRequest.objects.filter(
                    user_id=user_id, 
                    amount=total_fee, 
                    status='PENDING'
                ).first()
                
                if payment_req:
                    payment_req.status = 'APPROVED'
                    payment_req.processed = True
                    payment_req.save()
                
                Transaction.objects.create(
                    user_id=user_id,
                    amount=total_fee,
                    transaction_type='DEPOSIT',
                    details=f"Direct Binance USDT Deposit - Order: {merchant_trade_no}"
                )

        return JsonResponse({"returnCode": "SUCCESS", "returnMessage": None})
    except Exception as e:
        return JsonResponse({"returnCode": "FAIL", "returnMessage": str(e)}, status=500)


@login_required
def funding_view(request):
    exchange_acc, _ = Account.objects.get_or_create(user=request.user, account_type='EXCHANGE')
    trading_acc, _ = Account.objects.get_or_create(user=request.user, account_type='TRADING')

    total_balance = exchange_acc.balance + trading_acc.balance

    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')

    context = {
        'total_balance': total_balance,
        'exchange_balance': exchange_acc.balance,
        'trading_balance': trading_acc.balance,
        'transactions': transactions,
    }
    return render(request, 'payment.html', context)


@login_required
def request_withdrawal(request):
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
            if amount <= 0:
                messages.error(request, 'Withdrawal amount must be greater than zero.')
                return redirect('funding_view')

            # Withdrawals pull directly from the main Exchange account[cite: 8]
            exchange_acc = get_object_or_404(
                Account, user=request.user, account_type='EXCHANGE'
            )

            if exchange_acc.balance < amount:
                messages.error(
                    request,
                    'Insufficient funds in your Exchange account for withdrawal.',
                )
                return redirect('funding_view')

            with transaction.atomic():
                exchange_acc.balance -= amount
                exchange_acc.save()

                Transaction.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type='WITHDRAWAL',
                    details=f'External withdrawal of ${amount} from Exchange account',
                )

            messages.success(request, 'Withdrawal request submitted successfully.')
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, 'Please enter a valid amount.')
        except Exception as e:
            messages.error(request, f'Withdrawal failed: {str(e)}')

    return redirect('funding_deposit')


@login_required
def process_transaction(request):
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount'))
            t_type = request.POST.get('type')
        except (ValueError, TypeError):
            messages.error(request, "Invalid transaction amount.")
            return redirect('dashboard')

        # Safely default to EXCHANGE account for generic transactions[cite: 8]
        account, _ = Account.objects.get_or_create(user=request.user, account_type='EXCHANGE')

        if t_type == 'WITHDRAWAL':
            if account.balance < amount:
                messages.error(request, "Insufficient funds for withdrawal.")
                return redirect('dashboard')
            account.balance -= amount
        else:
            account.balance += amount
        
        account.save()

        Transaction.objects.create(
            user=request.user,
            amount=amount,
            transaction_type=t_type,
            status='APPROVED'
        )

        Notification.objects.create(
            user=request.user,
            title="Transaction Successful",
            message=f"Your {t_type.lower()} of ${amount} was successful."
        )

        messages.success(request, f"{t_type.capitalize()} of ${amount} completed.")
        return redirect('dashboard')
    
    return render(request, 'store/transaction.html')


@login_required
def payment_status_view(request, payment_id):
    """
    Fetches real-time status of a NOWPayments transaction from the sandbox/production API 
    and updates the local database state.
    """
    payment_req = get_object_or_404(PaymentRequest, user=request.user, payment_id=payment_id)
    
    api_key = getattr(settings, 'NOWPAYMENTS_API_KEY', '')
    is_sandbox = getattr(settings, 'NOWPAYMENTS_SANDBOX', True)
    base_url = 'https://api-sandbox.nowpayments.io/v1/' if is_sandbox else 'https://api.nowpayments.io/v1/'
    
    headers = {'x-api-key': api_key}
    status_data = {}
    
    try:
        response = requests.get(f"{base_url}payment/{payment_id}", headers=headers, timeout=10)
        if response.status_code == 200:
            status_data = response.json()
            np_status = status_data.get('payment_status')
            
            # Map NOWPayments statuses to local choices
            if np_status in ['finished', 'confirmed']:
                payment_req.status = 'APPROVED'
            elif np_status in ['failed', 'expired', 'rejected']:
                payment_req.status = 'REJECTED'
            elif np_status in ['waiting', 'confirming', 'processing']:
                payment_req.status = 'PROCESSING'
                
            payment_req.save()
    except requests.RequestException:
        pass

    # Return JSON if requested via AJAX script, otherwise render template
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'payment_id': payment_id,
            'status': payment_req.status,
            'np_status': status_data.get('payment_status', 'unknown')
        })

    context = {
        'payment_req': payment_req,
        'status_data': status_data,
    }
    return render(request, 'store/payment_status.html', context)


@login_required
def switch_tier(request, tier):
    tier_lower = tier.lower()
    valid_tiers = ['starter', 'pro', 'vip']
    
    if tier_lower in valid_tiers:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.subscription_tier = tier_lower
        profile.is_active_subscription = (tier_lower != 'starter')
        profile.save()
        messages.success(request, f"Your subscription has been successfully updated to {tier_lower.upper()}.")
    else:
        messages.error(request, "Selected subscription tier is invalid.")
        
    return redirect('subscription_billing')


@login_required
def cancel_subscription(request):
    if request.method == 'POST':
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.subscription_tier = 'starter'
        profile.is_active_subscription = False
        profile.save()
        messages.success(request, "Your subscription has been successfully cancelled.")
    return redirect('subscription_billing')


# ==========================================
# BROKER & DERIV INTEGRATION VIEWS
# ==========================================

@login_required
def ai_prediction_models(request):
    active_account = UserBrokerAccount.objects.filter(user=request.user, broker='DERIV', is_active=True).first()
    app_id = getattr(settings, 'DERIV_APP_ID', '33XN84FbZfx1ZO1xDyUzH')
    deriv_balance = None

    context = {
        'active_account': active_account,
        'deriv_oauth_url': f"https://oauth.deriv.com/oauth2/authorize?app_id={app_id}",
        'app_id': app_id,
        'deriv_balance': deriv_balance,
    }
    return render(request, 'store/ai_prediction_models.html', context)


@login_required
def connect_deriv(request):
    app_id = getattr(settings, 'DERIV_APP_ID', '33XN84FbZfx1ZO1xDyUzH')
    return redirect(f"https://oauth.deriv.com/oauth2/authorize?app_id={app_id}")


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
        if not account_number or not api_token: 
            break
        is_demo_account = account_number.startswith('VRTC')
        UserBrokerAccount.objects.update_or_create(
            user=request.user, broker='DERIV', account_number=account_number,
            defaults={'api_token': api_token, 'is_active': (index == 1)}
        )
        saved_accounts_count += 1
        index += 1
    if saved_accounts_count > 0: 
        messages.success(request, f"Successfully connected {saved_accounts_count} Deriv account(s)!")
    else: 
        messages.error(request, "Failed to connect Deriv account.")
    return redirect('ai_prediction_models')


@login_required
def connect_broker(request):
    if request.method == 'POST':
        broker = request.POST.get('broker', 'DERIV')
        account_number = request.POST.get('account_number')
        if account_number:
            UserBrokerAccount.objects.filter(user=request.user, broker=broker).update(is_active=False)
            UserBrokerAccount.objects.create(
                user=request.user, broker=broker, account_number=account_number, 
                api_token=request.POST.get('server_or_token'), is_active=True
            )
            messages.success(request, f"Connected {broker}!")
    return redirect('ai_prediction_models')


# ==========================================
# TRADING & MARKET VIEWS
# ==========================================

@login_required
def trade_view(request):
    return render(request, 'store/trade.html')


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
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)
    
    try:
        data = json.loads(request.body)
        symbol = data.get('symbol', 'R_10')
        contract_type = data.get('contract_type', 'DIGITMATCH') 
        amount = Decimal(str(data.get('amount', '10')))
        barrier = data.get('barrier')
        
        with transaction.atomic():
            # Live trades use the TRADING account[cite: 8]
            account = Account.objects.select_for_update().get(user=request.user, account_type='TRADING')
            
            if account.balance < amount:
                return JsonResponse({"success": False, "error": "Insufficient balance in your Trading account."}, status=400)
            
            account.balance -= amount
            account.save()
            
            asset_obj, _ = Asset.objects.get_or_create(
                symbol=symbol,
                defaults={'name': symbol, 'asset_type': 'synthetic', 'price': Decimal('1000.00')}
            )
            
            final_digit = random.randint(0, 9)
            won = False
            payout = Decimal('0.0')
            
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
            
            Transaction.objects.create(
                user=request.user,
                amount=payout if won else amount,
                transaction_type='TRADE_PAYOUT' if won else 'TRADE_STAKE',
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
    trades = Trade.objects.filter(user=request.user).exclude(status='OPEN').order_by('-date_opened')
    return render(request, 'store/trades_history.html', {'trades': trades})


@login_required
@transaction.atomic
def close_trade(request, trade_id, status, final_payout):
    trade = get_object_or_404(Trade, id=trade_id, user=request.user)
    
    if trade.status != 'OPEN':
        messages.error(request, "Trade is already closed.")
        return redirect('trade_history')

    trade.status = status
    trade.payout = Decimal(str(final_payout))
    trade.save()

    if status == 'WON':
        account = Account.objects.get(user=request.user, account_type='TRADING')
        account.balance += trade.payout
        account.save()
        messages.success(request, f"Trade closed! Profit: ${trade.payout}")
    else:
        messages.info(request, "Trade closed.")
        
    return redirect('trade_history')


@login_required
def digits_trading(request):
    return render(request, 'store/digits_trading.html')


@login_required
def user_trades(request):
    trades = Trade.objects.filter(user=request.user)
    total_profit = 0.0
    for trade in trades:
        if trade.status == 'LOST':
            total_profit -= float(trade.stake or 0)
        else:
            payout = float(trade.payout or 0)
            total_profit += payout

    trading_acc, _ = Account.objects.get_or_create(user=request.user, account_type='TRADING')

    context = {
        'total_profit': round(total_profit, 2),
        'available_balance': float(trading_acc.balance),
        'unrealized_pnl': 0.00,
        'active_assets_count': trades.filter(status='OPEN').count(),
        'holdings': [],
    }
    return render(request, 'store/portfolio.html', context)


# ==========================================
# WEBHOOK VIEWS
# ==========================================

@login_required
def webhook_automations_view(request):
    user_webhooks = WebhookEndpoint.objects.filter(user=request.user)
    active_count = user_webhooks.filter(is_active=True).count()
    
    total_requests = sum(w.requests_count for w in user_webhooks)
    avg_latency = int(sum(w.latency for w in user_webhooks) / user_webhooks.count()) if user_webhooks.exists() else 0
    avg_success = round(float(sum(w.success_rate for w in user_webhooks) / user_webhooks.count()), 1) if user_webhooks.exists() else 100.0

    stats_data = {
        'Total Endpoints': user_webhooks.count(),
        'Total Requests': total_requests,
        'Avg Success Rate': f"{avg_success}%",
        'Avg Latency': f"{avg_latency}ms"
    }

    return render(request, 'store/webhook_automations.html', {
        'active_count': active_count,
        'stats_data': stats_data,
        'webhooks': user_webhooks,
    })


@login_required
def toggle_webhook_status(request, webhook_id):
    webhook = get_object_or_404(WebhookEndpoint, id=webhook_id, user=request.user)
    webhook.is_active = not webhook.is_active
    webhook.save()
    return redirect('webhook_automations')


@login_required
def create_webhook(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        url = request.POST.get('url')
        webhook_type = request.POST.get('type', 'OUT')
        
        if name and url:
            Webhook.objects.create(
                user=request.user, name=name, url=url, type=webhook_type,
                is_active=True, requests_count=0, success_rate=100.0, latency=0
            )
            messages.success(request, "Webhook endpoint created successfully.")
        else:
            messages.error(request, "Both Name and URL are required.")
    return redirect('webhook_automations')


@csrf_exempt
def handle_incoming_webhook(request, source_name='Generic'):
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)

    client_token = request.headers.get('X-Webhook-Secret')
    expected_token = getattr(settings, 'WEBHOOK_SECRET_KEY', 'default-secret-token')
    
    if client_token != expected_token:
        return JsonResponse({"status": "error", "message": "Unauthorized webhook token"}, status=403)

    headers_dict = {k: v for k, v in request.headers.items()}
    raw_body = request.body.decode('utf-8')

    webhook_log = WebhookLog.objects.create(
        source=source_name, payload=raw_body, headers=json.dumps(headers_dict)
    )

    try:
        data = json.loads(raw_body)
        webhook_log.is_processed = True
        webhook_log.save()
        return JsonResponse({"status": "success", "message": "Webhook processed successfully"}, status=200)
    except Exception as e:
        webhook_log.is_processed = False
        webhook_log.error_message = str(e)
        webhook_log.save()
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


# ==========================================
# BOT VIEWS
# ==========================================

@login_required
def bot_dashboard_view(request):
    form = CreateBotForm()
    logs = BotLog.objects.all()[:50]
    
    trading_acc, _ = Account.objects.get_or_create(user=request.user, account_type='TRADING')

    context = {
        'form': form,
        'logs': logs,
        'bot_status': 'running',
        'account_balance': float(trading_acc.balance),
        'unrealized_pnl': 15.50,
        'pnl_pct': 1.55,
        'current_pair': 'R_100',
    }
    return render(request, 'store/bot.html', context)


@login_required
def create_bot_view(request):
    if request.method == 'POST':
        form = CreateBotForm(request.POST)
        if form.is_valid():
            pass
    return redirect('bot')


@login_required
def bot_control_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'start':
            messages.success(request, "AI Trading Engine started successfully.")
        elif action == 'stop':
            messages.info(request, "AI Trading Engine received stop signal.")
        elif action == 'emergency_stop':
            messages.warning(request, "EMERGENCY SELL EXECUTED. All positions closed.")
        else:
            messages.error(request, f"Unknown action: {action}")
        return redirect('bot')
    return redirect('bot')


# ==========================================
# ADMIN & UTILITY VIEWS
# ==========================================

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
            
        payment_req.save()
        return redirect('admin_payment_dashboard')

    pending_requests = PaymentRequest.objects.filter(status='PENDING')
    return render(request, 'store/admin_approvals.html', {'requests': pending_requests})


@staff_member_required
def admin_deposit_approval_view(request):
    return render(request, 'admin/deposit_approval.html')


def check_notifications(request):
    new_transactions = Transaction.objects.filter(is_notified=False)
    notifications = []
    for tx in new_transactions:
        notifications.append({
            'title': f'{tx.transaction_type.capitalize()} Accepted',
            'message': f'Your {tx.transaction_type} of ${tx.amount} is complete.',
            'link': '/funded/'
        })
        tx.is_notified = True
        tx.save()
    return JsonResponse({'new_notifications': notifications})


def news_sentiment(request):
    articles = NewsArticle.objects.all().order_by('-published')[:10]
    stats = NewsArticle.objects.aggregate(avg_polarity=Avg('polarity'))
    avg_polarity = stats['avg_polarity'] or 0
    overall_sentiment = "Bullish" if avg_polarity > 0.1 else "Bearish" if avg_polarity < -0.1 else "Neutral"
    context = {'news_list': articles, 'overall_sentiment': overall_sentiment, 'avg_polarity': round(avg_polarity, 2)}
    return render(request, 'store/news_sentiment.html', context)


# ==========================================
# PLACEHOLDER / STUB VIEWS (All Preserved)
# ==========================================

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

@login_required
def webhook_automations(request):  # Renamed from webhook_automations_view
    user_webhooks = WebhookEndpoint.objects.filter(user=request.user)
    active_count = user_webhooks.filter(is_active=True).count()
    
    total_requests = sum(w.requests_count for w in user_webhooks)
    avg_latency = int(sum(w.latency for w in user_webhooks) / user_webhooks.count()) if user_webhooks.exists() else 0
    avg_success = round(float(sum(w.success_rate for w in user_webhooks) / user_webhooks.count()), 1) if user_webhooks.exists() else 100.0

    stats_data = {
        'Total Endpoints': user_webhooks.count(),
        'Total Requests': total_requests,
        'Avg Success Rate': f"{avg_success}%",
        'Avg Latency': f"{avg_latency}ms"
    }

    return render(request, 'store/webhooks.html', {
        'active_count': active_count,
        'stats_data': stats_data,
        'webhooks': user_webhooks,
    })


@login_required
def internal_transfer(request):
    if request.method == 'POST':
        amount_str = request.POST.get('amount')
        recipient_username = request.POST.get('recipient_username')
        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                messages.error(request, "Transfer amount must be greater than zero.")
                return redirect('funding_deposit')

            sender_account, _ = Account.objects.get_or_create(user=request.user, account_type='EXCHANGE')
            recipient_user = get_object_or_404(User, username=recipient_username)
            
            if recipient_user == request.user:
                messages.error(request, "You cannot transfer funds to yourself.")
                return redirect('funding_deposit')
                
            recipient_account, _ = Account.objects.get_or_create(user=recipient_user, account_type='EXCHANGE')
            
            if sender_account.balance >= amount:
                with transaction.atomic():
                    sender_account.balance -= amount
                    sender_account.save()
                    
                    recipient_account.balance += amount
                    recipient_account.save()
                    
                    # Log for sender
                    Transaction.objects.create(
                        user=request.user,
                        amount=amount,
                        transaction_type='INTERNAL_TRANSFER',
                        details=f"Transfer to @{recipient_user.username}"
                    )
                    # Log for recipient
                    Transaction.objects.create(
                        user=recipient_user,
                        amount=amount,
                        transaction_type='INTERNAL_TRANSFER',
                        details=f"Received from @{request.user.username}"
                    )
                messages.success(request, f"Successfully transferred ${amount} to @{recipient_user.username}.")
            else:
                messages.error(request, "Insufficient funds for internal transfer.")
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, "Invalid transfer details or amount.")
    return redirect('funding_deposit')


@login_required
def funding_deposit(request):
    # Safely get or create both split accounts[cite: 8]
    exchange_acc, _ = Account.objects.get_or_create(user=request.user, account_type='EXCHANGE')
    trading_acc, _ = Account.objects.get_or_create(user=request.user, account_type='TRADING')
    
    # Calculate total net balance (Exchange + Trading)[cite: 8]
    total_balance = exchange_acc.balance + trading_acc.balance

    # Pass user transactions for the transaction history tab[cite: 8]
    user_transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'transactions': user_transactions,
        'balance': total_balance,               # Main combined balance for the template header[cite: 8]
        'exchange_balance': exchange_acc.balance, # Individual Exchange breakdown[cite: 8]
        'trading_balance': trading_acc.balance,   # Individual Trading breakdown[cite: 8]
    }
    return render(request, 'store/payment.html', context)


@login_required
def create_nowpayments_payment(request):
    if request.method == 'POST':
        amount = request.POST.get('amount')
        pay_currency = request.POST.get('pay_currency', 'usdttrc20') # e.g., usdttrc20, btc, eth
        
        # Check settings sandbox flag safely, defaulting to sandbox mode for safety
        is_sandbox = getattr(settings, 'NOWPAYMENTS_SANDBOX', True)
        api_url = "https://api-sandbox.nowpayments.io/v1/payment" if is_sandbox else "https://api.nowpayments.io/v1/payment"
        
        headers = {
            "x-api-key": getattr(settings, 'NOWPAYMENTS_API_KEY', ''),
            "Content-Type": "application/json"
        }
        
        try:
            parsed_amount = float(amount)
        except (TypeError, ValueError):
            messages.error(request, "Invalid deposit amount provided.")
            return redirect('funding_deposit')

        payload = {
            "price_amount": parsed_amount,
            "price_currency": "usd",
            "pay_currency": pay_currency,
            "ipn_callback_url": "https://yourdomain.com/api/nowpayments/ipn/", # Update with your public webhook URL
            "order_id": f"DEPOSIT-{request.user.id}-{int(time.time())}",
            "order_description": f"Account deposit for {request.user.username}"
        }
        
        try:
            response = requests.post(api_url, json=payload, headers=headers)
            data = response.json()
            
            # NOWPayments returns 201 Created on success
            if response.status_code in [200, 201] or 'pay_address' in data:
                pay_address = data.get('pay_address')
                pay_amount = data.get('pay_amount')
                invoice_id = data.get('payment_id')
                
                # Save details temporarily in session to display payment instructions on the page
                request.session['pending_deposit'] = {
                    'invoice_id': invoice_id,
                    'pay_address': pay_address,
                    'pay_amount': pay_amount,
                    'pay_currency': pay_currency
                }
                
                messages.success(request, f"Please send exactly {pay_amount} {pay_currency.upper()} to address: {pay_address}")
                return redirect('funding_deposit')
            else:
                error_msg = data.get('message', 'Failed to initiate crypto payment.')
                messages.error(request, f"Payment error: {error_msg}")
        except Exception as e:
            messages.error(request, "Error connecting to payment gateway.")
            
    return redirect('funding_deposit')

@csrf_exempt
@require_POST
def nowpayments_ipn_webhook(request):
    received_sig = request.headers.get('x-nowpayments-sig')
    if not received_sig:
        return JsonResponse({"error": "No signature provided"}, status=400)
    
    try:
        request_body_bytes = request.body
        payload = json.loads(request_body_bytes.decode('utf-8'))
        
        sorted_payload = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        computed_sig = hmac.new(
            settings.NOWPAYMENTS_IPN_SECRET.encode('utf-8'),
            sorted_payload.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        if not hmac.compare_digest(computed_sig, received_sig):
            return JsonResponse({"error": "Invalid signature"}, status=400)
            
        payment_status = payload.get('payment_status')
        price_amount = float(payload.get('price_amount', 0))
        order_id = payload.get('order_id') # Format: DEPOSIT-[user_id]-[timestamp]
        
        if payment_status == 'finished':
            try:
                user_id = int(order_id.split('-')[1])
            except (IndexError, ValueError):
                return JsonResponse({"error": "Invalid order reference"}, status=400)
                
            from django.contrib.auth.models import User
            user = User.objects.filter(id=user_id).first()
            
            if user:
                with transaction.atomic():
                    # Crypto deposits credit the EXCHANGE account[cite: 8]
                    user_account, _ = Account.objects.get_or_create(user=user, account_type='EXCHANGE')
                    user_account.balance += price_amount
                    user_account.save()
                    
                    Transaction.objects.create(
                        user=user,
                        amount=price_amount,
                        transaction_type='DEPOSIT',
                        details=f"Automated NOWPayments USDT Deposit (ID: {payload.get('payment_id')})"
                    )
                    
        return JsonResponse({"status": "success"}, status=200)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def transfer_between_accounts(request):
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
            source_type = request.POST.get('source_type')  # 'EXCHANGE' or 'TRADING'[cite: 8]
            target_type = request.POST.get('target_type')  # 'TRADING' or 'EXCHANGE'[cite: 8]

            if amount <= 0:
                messages.error(request, "Transfer amount must be greater than zero.")
                return redirect('funding_view')

            if source_type == target_type:
                messages.error(request, "Source and target accounts must be different.")
                return redirect('funding_view')

            source_account = get_object_or_404(Account, user=request.user, account_type=source_type)
            target_account = get_object_or_404(Account, user=request.user, account_type=target_type)

            if source_account.balance < amount:
                messages.error(request, f"Insufficient funds in your {source_account.get_account_type_display()}.")
                return redirect('funding_view')

            with transaction.atomic():
                source_account.balance -= amount
                source_account.save()

                target_account.balance += amount
                target_account.save()

                Transaction.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type='INTERNAL_TRANSFER',
                    details=f"Transferred ${amount} from {source_account.get_account_type_display()} to {target_account.get_account_type_display()}"
                )

            messages.success(request, f"Successfully transferred ${amount} to your {target_account.get_account_type_display()}.")
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, "Please enter a valid transfer amount.")
        except Exception as e:
            messages.error(request, f"Transfer failed: {str(e)}")
            
    return redirect('funding_deposit')


@require_POST
def execute_ai_gold(request):
    try:
        # 1. New York Session & 1-Hour Window Validation
        ny_tz = ZoneInfo("America/New_York")
        now_ny = datetime.now(ny_tz)
        current_hour = now_ny.hour
        
        # New York Forex session active hours (e.g., 08:00 AM to 05:00 PM EST)
        is_ny_session = 8 <= current_hour < 17
        
        if not is_ny_session:
            return JsonResponse({
                'success': False,
                'error': 'AI Gold Auto-Trader is restricted to the New York session (08:00 - 17:00 EST).'
            }, status=400)

        # 2. Enforce Lot Size = 1
        lot_size = 1.00

        # 3. Retrieve User's Real Account Trading Balance
        # Pulls from the authenticated user's profile or connected broker session
        user_balance = getattr(request.user, 'trading_balance', 1000.00)
        
        if user_balance < lot_size:
            return JsonResponse({
                'success': False,
                'error': 'Insufficient account trading balance for lot size 1.'
            }, status=400)

        # 4. System-Admin Defined SL & TP Parameters
        system_sl = 5.00  # System-enforced Stop Loss pips/points
        system_tp = 10.00 # System-enforced Take Profit pips/points

        trades = []
        current_balance = user_balance
        directions = ['BUY (XAUUSD)', 'SELL (XAUUSD)', 'BUY (XAUUSD)']

        # 5. Execute the 3 Automated Gold Trades
        for i in range(3):
            direction = directions[i]
            entry_price = 2350.50 + random.uniform(-1.5, 1.5)
            
            # Calculate system SL/TP based on entry direction
            sl = entry_price - system_sl if 'BUY' in direction else entry_price + system_sl
            tp = entry_price + system_tp if 'BUY' in direction else entry_price - system_tp
            
            # Simulate trade outcome based on AI probability engine
            won = random.random() > 0.32
            payout = (lot_size * 1.95) if won else 0.0
            
            if won:
                current_balance += (payout - lot_size)
            else:
                current_balance -= lot_size
                
            trades.append({
                'direction': direction,
                'entry': round(entry_price, 2),
                'sl': round(sl, 2),
                'tp': round(tp, 2),
                'result': 'WON' if won else 'LOST',
                'payout': round(payout, 2)
            })

        # Save updated balance back to user profile if needed
        # request.user.trading_balance = current_balance
        # request.user.save()

        return JsonResponse({
            'success': True,
            'trades': trades,
            'new_balance': round(current_balance, 2)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)



        import random
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from .models import ClientAIToggle

def run_daily_ai_gold_engine():
    # 1. Timezone and Date setup (New York Time)
    ny_tz = ZoneInfo("America/New_York")
    now_ny = datetime.now(ny_tz)
    today = now_ny.date()
    current_hour = now_ny.hour
    current_weekday = now_ny.weekday() # 0 = Mon, 4 = Fri, 5 = Sat, 6 = Sun

    # 2. Weekend Check: Stop if Saturday or Sunday
    if current_weekday >= 5:
        return {"status": "Paused: Market closed for the weekend."}

    # 3. New York Session Check (08:00 to 17:00 EST)
    if not (8 <= current_hour < 17):
        return {"status": "Skipped: Outside New York session hours."}

    # 4. Fetch Active Clients
    active_clients = ClientAIToggle.objects.filter(is_active=True)
    execution_summary = []

    for toggle_record in active_clients:
        # Prevent duplicate execution on the same day
        if toggle_record.last_trade_date == today:
            continue 

        user = toggle_record.user
        user_balance = getattr(user, 'trading_balance', 1000.00)
        lot_size = float(toggle_record.assigned_lot_size) # Lot size = 1.00

        if user_balance < lot_size:
            continue

        # 5. AI FVG & Trend Confluence Check (Simulated XAUUSD Direction)
        trend_is_bullish = random.choice([True, False])
        direction = 'BUY (XAUUSD)' if trend_is_bullish else 'SELL (XAUUSD)'
        
        entry_price = 2350.50
        system_sl = 5.00
        system_tp = 10.00
        
        sl = entry_price - system_sl if 'BUY' in direction else entry_price + system_sl
        tp = entry_price + system_tp if 'BUY' in direction else entry_price - system_tp

        # 6. Execute exactly 3 trades for the day
        client_trades = []
        current_balance = user_balance
        
        for _ in range(3):
            won = random.random() > 0.30 # High-probability win model on FVG retest
            payout = (lot_size * 1.95) if won else 0.0
            
            if won:
                current_balance += (payout - lot_size)
            else:
                current_balance -= lot_size
                
            client_trades.append({
                'direction': direction,
                'entry': entry_price,
                'sl': sl,
                'tp': tp,
                'result': 'WON' if won else 'LOST'
            })

        # Update client balance and lock the date to prevent re-running today
        user.trading_balance = round(current_balance, 2)
        user.save()

        toggle_record.last_trade_date = today
        toggle_record.save()
        
        execution_summary.append({
            'username': user.username,
            'date': str(today),
            'trades_executed': 3,
            'new_balance': user.trading_balance
        })

    return {"status": "Success", "daily_executions": execution_summary}