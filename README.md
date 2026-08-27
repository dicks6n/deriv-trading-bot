@login_required
def request_withdrawal(request):
    if request.method == 'POST':
        amount_str = request.POST.get('amount')
        method = request.POST.get('method', 'Bank Card')
        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                messages.error(request, "Withdrawal amount must be greater than zero.")
                return redirect('funding_deposit')

            user_account, _ = Account.objects.get_or_create(user=request.user)
            
            if user_account.balance >= amount:
                with transaction.atomic():
                    user_account.balance -= amount
                    user_account.save()
                    
                    Transaction.objects.create(
                        user=request.user,
                        amount=amount,
                        transaction_type='WITHDRAWAL',
                        details=f"Withdrawal via {method}"
                    )
                messages.success(request, f"Withdrawal of ${amount} processed successfully.")
            else:
                messages.error(request, "Insufficient funds for withdrawal.")
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, "Invalid withdrawal amount.")
    return redirect('funding_deposit')