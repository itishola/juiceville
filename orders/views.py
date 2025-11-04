# orders/views.py

import json
import uuid
import xlwt
import csv

from django.db.models import Count, Sum
from datetime import date, datetime, timedelta
from calendar import monthrange

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone

from decimal import Decimal
from django.conf import settings
from paystackapi.paystack import Paystack

from users.models import Customer, Staff
from items.models import Item, Combo
from orders.models import Order, OrderedItem, DeliveryLocation, OperatingHours
from items.constants import CATEGORIES
from orders.forms import OfferForm
from .notifications import send_telegram_alert
from orders.utils import *

def index(request):
    return render(request, 'orders/index.html')

def test_menu(request):
    ck_items = []
    ps_items = []
    js_items = []
    dr_items = []
    fd_items = []
    pr_items = []
    ss_items = []
    ml_items = []
    dt_items = []
    pc_items = []

    context = {
        'ck_items' : [],
        'ps_items' : [],
        'js_items' : [],
        'dr_items' : [],
        'fd_items' : [],
        'pr_items' : [],
        'ss_items' : [],
        'ml_items' : [],
        'dt_items' : [],
        'pc_items' : [],
    }

    for item in Item.objects.filter(stock__gte=1):
        category = (item.category).lower()
        context.setdefault(category + "_items", []).append(item)

    # 3. Calculate available Combos
    all_combos = Combo.objects.all()
    available_combos = [combo for combo in all_combos if combo.effective_stock > 0] 

    # 🛑 CRITICAL FIX: Add combos to the EXISTING context dictionary
    # You MUST REMOVE the entire block where you were overwriting context before.
    context['available_combos'] = available_combos 

    return render(request, 'orders/menu-1.html', context)

def is_managing_director(user):
    """Check if user is Managing Director"""
    if not user.is_authenticated:
        return False
    # Check if superuser or in Managing Director group or has MG designation
    return (user.is_superuser or 
            user.groups.filter(name='Managing Director').exists() or
            (hasattr(user, 'staff') and user.staff.designation in ['MD', 'MG']))

@login_required
def create_order(request):
    customer = get_object_or_404(Customer, user=request.user)
    
    # Setup datetime variables
    now = datetime.now()
    current_day = now.weekday() # Monday=0, Sunday=6
    current_date = now.date()
    now_time = now.time()

    schedule = None
    
    # 1. ATTEMPT HOLIDAY OVERRIDE FIRST (Highest priority)
    try:
        schedule = OperatingHours.objects.get(closed_date=current_date)
    except OperatingHours.DoesNotExist:
        try:
            # 2. If no holiday override, check the standard day-of-the-week schedule
            schedule = OperatingHours.objects.get(day=current_day, closed_date__isnull=True)
        except OperatingHours.DoesNotExist:
            # 3. No schedule found. Allows ordering but warns staff.
            messages.warning(request, f'Warning: Operating hours for {now.strftime("%A")} have not been set. Ordering allowed by default.')
            pass # Schedule remains None, allowing code to proceed

    # CHECK RESTRICTIONS
    if schedule:
        if not schedule.is_open:
            # Case 1: Explicitly closed all day (Holiday or Day-of-Week)
            reason = "due to a scheduled closure"
            if schedule.closed_date:
                 reason = "due to a Public Holiday or scheduled closure"
            elif schedule.day is not None:
                reason = f"all day on {schedule.get_day_display()}"
                
            messages.error(request, f'Ordering is currently closed {reason}.')
            return redirect('index')
        
        # Case 2: Open, but check time window
        
        # CRITICAL: Check for configuration validity (must have times if open)
        if schedule.opening_time is None or schedule.closing_time is None:
            messages.error(request, 'Configuration Error: Operating hours are marked as OPEN but missing specific times. Ordering blocked. Please contact staff.')
            return redirect('index')
            
        # Actual time check
        if not (schedule.opening_time <= now_time <= schedule.closing_time):
            open_str = schedule.opening_time.strftime('%I:%M %p')
            close_str = schedule.closing_time.strftime('%I:%M %p')
            messages.error(
                request, 
                f'Ordering is closed. We are open from {open_str} to {close_str} today.'
            )
            return redirect('index')
                    
    # 3. NEW ENFORCEMENT LOGIC: Check for profile completion (Mandatory)
    if not customer.name or not customer.address or not customer.phone or not customer.delivery_location:
        messages.error(request, 'Please complete your profile details (Name, Phone, Address, and Delivery Region) before placing an order.')
        return redirect('customer_profile')
    
    # CRITICAL FIX: Fetch the specific delivery fee from the customer's chosen location
    delivery_fee = customer.delivery_location.fee if customer.delivery_location else Decimal('0.00')
    
    # 4. Create the Order
    order = Order.objects.create(
        customer=customer,
        delivery_fee=delivery_fee 
    )
    
    return redirect('orders:add_items', pk=order.id)

@login_required
def add_items(request, pk):
    order = get_object_or_404(Order, pk=pk)
    
    try:
        customer = request.user.customer
        if customer.delivery_location:
            delivery_fee = customer.delivery_location.fee
        else:
            delivery_fee = Decimal('0.00')
    except Exception:
        delivery_fee = Decimal('0.00')

    if request.method == "POST":
        print("POST request received - Processing items and combos")
        
        data = request.POST 
        items = Item.objects.all()
        combos = Combo.objects.all()
        items_added_count = 0 
        combos_added_count = 0 

        # PROCESS INDIVIDUAL ITEMS
        for item in items:
            item_quantity_list = data.getlist(str(item.id))
            item_quantity_str = item_quantity_list[0] if item_quantity_list else '0'
            item_quantity = 0
            
            if item_quantity_str:
                try:
                    item_quantity = int(item_quantity_str)
                except ValueError:
                    continue 

            if item_quantity > 0:
                ordered_item, created = OrderedItem.objects.get_or_create(
                    order=order,
                    item=item,
                    combo=None, 
                    defaults={'quantity': item_quantity}
                )

                if not created:
                    ordered_item.quantity += item_quantity
                    ordered_item.save()

                ordered_item.calculate_price()
                items_added_count += 1
                print(f"Added {item_quantity} of {item.name} to order")

        # PROCESS COMBO ITEMS
        for combo in combos:
            combo_key = f"combo_{combo.id}"
            combo_quantity_str = data.get(combo_key, '0') 
            combo_quantity = 0

            if combo_quantity_str:
                try:
                    combo_quantity = int(combo_quantity_str)
                except ValueError:
                    continue

            # Only add combos with explicit quantity > 0
            if combo_quantity > 0:
                ordered_combo, created = OrderedItem.objects.get_or_create(
                    order=order,
                    combo=combo, 
                    item=None,
                    defaults={'quantity': combo_quantity}
                )
                
                if not created:
                    ordered_combo.quantity += combo_quantity
                    ordered_combo.save()
                    
                ordered_combo.calculate_price()
                combos_added_count += 1 
                print(f"Added {combo_quantity} of COMBO {combo.name} to order")

        # FORCE RECALCULATION OF ORDER TOTALS
        order.refresh_totals()
        
        # Feedback
        total_added = items_added_count + combos_added_count
        if total_added > 0:
            messages.success(request, f'🎉 {total_added} item(s)/combo(s) added to Order!')
        else:
            messages.warning(request, 'No items were selected or quantity was zero.')
        
        return redirect('orders:add_items', pk=order.id)
    
    # For GET requests, ensure totals are calculated
    order.refresh_totals()
    ordered_items = OrderedItem.objects.filter(order=order)

    context = {
        'order': order,
        'ordered_items': ordered_items,
        'available_combos': Combo.objects.all(),
        'ck_items': Item.objects.filter(category='CK', stock__gte=1),
        'ps_items': Item.objects.filter(category='PS', stock__gte=1),
        'js_items': Item.objects.filter(category='JS', stock__gte=1),
        'ds_items': Item.objects.filter(category='DS', stock__gte=1),
        'dr_items': Item.objects.filter(category='DR', stock__gte=1),
        'fd_items': Item.objects.filter(category='FD', stock__gte=1),
        'pr_items': Item.objects.filter(category='PR', stock__gte=1),
        'ss_items': Item.objects.filter(category='SS', stock__gte=1),
        'ml_items': Item.objects.filter(category='ML', stock__gte=1),
        'dt_items': Item.objects.filter(category='DT', stock__gte=1),
        'pc_items': Item.objects.filter(category='PC', stock__gte=1),
    }

    return render(request, 'orders/menu.html', context)


@login_required
def apply_loyalty_points(request, pk):
    order = get_object_or_404(Order, pk=pk)
    customer = request.user.customer

    if customer.loyalty_points >= 50:
        order.used_loyalty_points = True
        messages.success(request, 'Loyalty points redeemed! You will receive a discount on finalizing the order.')
    else:
        messages.error(request, 'You do not have enough loyalty points to redeem.')

    order.save()
    return redirect('orders:add_items', order.id)

@login_required
def finalize_order(request, pk):
    order = get_object_or_404(Order, pk=pk)
    ordered_items = OrderedItem.objects.filter(order=order)
    customer = request.user.customer

    if not order.payment_reference:
        messages.error(request, 'Please proceed with payment before finalizing the order.')
        return redirect('orders:add_items', order.id)

    paystack = Paystack(secret_key=settings.PAYSTACK_SECRET_KEY)
    verification_response = paystack.transaction.verify(order.payment_reference)

    if verification_response['status'] and verification_response['data']['status'] == 'success':
        if len(ordered_items):
            order.date_placed = date.today()
            order.time_placed = datetime.now()
            
            # Calculate final total with loyalty discount
            subtotal = sum(item.price for item in ordered_items)
            delivery_fee = order.delivery_fee
            
            if order.used_loyalty_points and customer.loyalty_points >= 50:
                discount = Decimal('2500.00')
                customer.loyalty_points -= 50
                messages.success(request, 'Loyalty points redeemed for a ₦2500 discount!')
            else:
                discount = Decimal('0.00')
                points_earned = int(subtotal) // 1000
                customer.loyalty_points += points_earned
                messages.success(request, f'You earned {points_earned} loyalty points!')

            order.grand_total = max(subtotal + delivery_fee - discount, Decimal('0.00'))
            customer.save()
            
            # Update stocks
            calculate_grand_total_and_update_stocks(order, ordered_items)
            calculate_expected_delivery_time(order)
            order.finalized = True
            order.save()

            print("ATTEMPTING TO SEND TELEGRAM ALERT NOW (Finalize Order)...")
            send_telegram_alert(order) 

            messages.success(request, 'Order Cooking!')
            return redirect('orders:order_summary', order.id)
        else:
            return redirect('orders:add_items', order.id)
    else:
        messages.error(request, 'Payment verification failed. Please try again.')
        return redirect('orders:add_items', order.id)

@login_required
def initiate_payment(request, pk):
    order = get_object_or_404(Order, pk=pk)
    customer = request.user.customer

    if len(OrderedItem.objects.filter(order=order)) == 0:
        messages.error(request, 'Cannot initiate payment for an empty order.')
        return redirect('orders:add_items', order.id)

    # Recalculate grand total to ensure accuracy before payment
    ordered_items = OrderedItem.objects.filter(order=order)
    subtotal = sum(item.price for item in ordered_items)
    delivery_fee = order.delivery_fee # Use the delivery fee from the order object
    discount = Decimal('0.00')

    if order.used_loyalty_points and customer.loyalty_points >= 50:
        discount = Decimal('2500.00')

    # FIX: Add delivery_fee to the final_total
    final_total = max(subtotal + delivery_fee - discount, Decimal('0.00'))
    order.grand_total = final_total
    order.save()

    paystack = Paystack(secret_key=settings.PAYSTACK_SECRET_KEY)

    # Paystack amount is in kobo (100 kobo = 1 Naira)
    amount_kobo = int(final_total * 100)

    # Generate a unique payment reference
    payment_reference = str(uuid.uuid4())

    order.payment_reference = payment_reference
    order.save()

    payment_data = {
        "email": customer.user.email,
        "amount": amount_kobo,
        "reference": payment_reference,
        "callback_url": request.build_absolute_uri(reverse('orders:finalize_order', args=[order.id])),
    }

    try:
        response = paystack.transaction.initialize(**payment_data)
        if response.get('status'):
            return redirect(response['data']['authorization_url'])
        else:
            messages.error(request, response.get('message', 'Failed to initiate payment. Please try again.'))
    except Exception as e:
        messages.error(request, f'An error occurred: {e}')

    return redirect('orders:add_items', order.id)

@login_required
def delete_order(request, pk):
    try:
        Order.objects.filter(id=pk).delete()
        messages.success(request, 'Order Cancelled')
        return redirect('orders:index')
    except:
        return redirect('orders:index')

@login_required
def order_summary(request, pk):
    order = get_object_or_404(Order, pk=pk)
    
    # Force recalculation before displaying
    order.refresh_totals()
    ordered_items = OrderedItem.objects.filter(order=order)

    # Debug output
    print("=== ORDER SUMMARY DEBUG ===")
    print(f"Order ID: {order.id}")
    print(f"Subtotal: {order.subtotal}")
    print(f"Delivery Fee: {order.delivery_fee}")
    print(f"Loyalty Discount Applied: {order.used_loyalty_points}")
    print(f"Grand Total: {order.grand_total}")
    
    for item in ordered_items:
        if item.item:
            print(f"Item: {item.item.name}, Qty: {item.quantity}, Price: {item.price}")
        elif item.combo:
            print(f"Combo: {item.combo.name}, Qty: {item.quantity}, Price: {item.price}")
    print("===========================")

    context = {
        'order': order,
        'items': ordered_items
    }

    return render(request, 'orders/order_summary.html', context)

# --- STAFF DASHBOARD VIEW ---
@staff_member_required
def staff_dashboard(request):
    
    user = request.user
    
    # Staff object creation/lookup logic
    if not Staff.objects.filter(user=user).exists():
        staff = Staff.objects.create(
            user=user,
            name=user.username,
            email=user.email,
            designation='AD' 
        )
    else:
        staff = get_object_or_404(Staff, user=user)
    
    # Render the initial dashboard template
    return render(request, 'users/staff_dashboard.html', {
        'staff': staff,
        # Passes the fully rendered HTML snippet for the order list
        'pending_orders_html': _render_pending_orders(request),
    })

# --- CLOSE ORDER VIEW (NOW HANDLES HTMX) ---
@login_required
@staff_member_required
@require_POST # Ensure only POST requests are processed
def close_order(request, pk):
    # Ensure staff object is retrieved, or use a custom decorator/middleware
    # for cleaner user profile access if available.
    staff = get_object_or_404(Staff, user=request.user)
    
    # 1. Check staff permissions
    if staff.designation in ['CS', 'KS', 'MG', 'MD']:
        order = get_object_or_404(Order, pk=pk)
        
        # 2. Update order status
        order.delivered = True
        order.save()
        
        # OPTIONAL: Add loyalty points logic here...
        
        # 3. Add success message (now visible because we redirect to a full page)
        messages.success(request, f"Order #{order.pk} has been marked as delivered and closed.")
        
        # 4. Redirect to the staff dashboard to refresh the list
        return redirect('staff_dashboard') 
        
    else:
        # If permission check fails, add an error message and redirect home or to dashboard
        messages.error(request, "You do not have permission to close orders.")
        return redirect('staff_dashboard') 
    
@login_required
def past_transactions(request):

    customer = get_object_or_404(Customer, user = request.user)
    # Order by date placed descending to show most recent first
    orders = Order.objects.filter(customer = customer, finalized = True).order_by('-date_placed') 

    # Implement Pagination
    paginator = Paginator(orders, 10) # 10 orders per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'customer' : customer, 
        'page_obj': page_obj, 
    }

    # CRITICAL FIX: Ensure the template name exactly matches the file name.
    # It should be 'orders/customer_past_transactions.html'
    return render(request, 'orders/customer_past_transactions.html', context) 

@login_required
@require_POST
def hide_order(request, pk):
    """
    Hide a specific order from customer view
    """
    try:
        order = get_object_or_404(Order, pk=pk, customer=request.user.customer)
        order.hidden_from_customer = True
        order.save()
        
        return JsonResponse({'success': True, 'message': 'Order hidden from view'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def cleanup_orders(request):
    """
    Bulk cleanup of customer orders based on selected option
    """
    try:
        customer = request.user.customer
        data = json.loads(request.body)
        action = data.get('action')
        
        if action == 'hide_delivered':
            # Hide all delivered orders
            Order.objects.filter(customer=customer, delivered=True).update(hidden_from_customer=True)
            message = 'All delivered orders have been hidden from your view.'
            
        elif action == 'hide_old':
            # Hide orders older than 30 days
            cutoff_date = timezone.now() - timezone.timedelta(days=30)
            Order.objects.filter(customer=customer, date_placed__lt=cutoff_date).update(hidden_from_customer=True)
            message = 'Orders older than 30 days have been hidden.'
            
        elif action == 'show_all':
            # Show all orders
            Order.objects.filter(customer=customer).update(hidden_from_customer=False)
            message = 'All orders are now visible.'
            
        else:
            return JsonResponse({'success': False, 'error': 'Invalid action'})
        
        return JsonResponse({'success': True, 'message': message})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def customer_past_transactions(request):
    """
    Safe version that handles missing hidden_from_customer column
    """
    try:
        customer = request.user.customer
    except Customer.DoesNotExist:
        return render(request, 'orders/error.html', {
            'message': 'Customer profile not found. Please contact support.'
        })
    
    # SAFE APPROACH: Get all orders first, then filter in Python
    try:
        # Try database filtering first (if column exists)
        past_transactions = Order.objects.filter(
            customer=customer,
            finalized=True,
            hidden_from_customer=False
        ).order_by('-date_placed')
        
        # Test if the query works by checking one record
        if past_transactions.exists():
            _ = past_transactions.first().hidden_from_customer
            
    except (OperationalError, FieldError) as e:
        # If column doesn't exist, fall back to showing all orders
        print(f"Column not found, using fallback: {e}")
        past_transactions = Order.objects.filter(
            customer=customer,
            finalized=True
        ).order_by('-date_placed')
    
    # Calculate loyalty points statistics (simplified - no total spent)
    total_orders = Order.objects.filter(customer=customer, finalized=True).count()
    earned_points = customer.loyalty_points
    points_used = Order.objects.filter(
        customer=customer, 
        finalized=True, 
        used_loyalty_points=True
    ).count() * 50
    
    # Check if cleanup features are available
    cleanup_available = hasattr(Order.objects.first(), 'hidden_from_customer') if Order.objects.exists() else False
    
    paginator = Paginator(past_transactions, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'customer': customer,
        'past_transactions': page_obj,
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'total_orders': total_orders,
        'earned_points': earned_points,
        'points_used': points_used,
        'cleanup_available': cleanup_available,
    }
    return render(request, 'orders/customer_past_transactions.html', context)

@login_required
def transaction_detail(request, order_id):
    try:
        # If the user is staff, they can view any order
        if request.user.is_staff:
            order = Order.objects.get(id=order_id)
        else:
            # For non-staff, they must have a customer profile and the order must belong to them
            customer = request.user.customer
            order = Order.objects.get(id=order_id, customer=customer)
    
    except (Order.DoesNotExist, Customer.DoesNotExist) as e:
        # Handle the error appropriately
        if isinstance(e, Order.DoesNotExist):
            messages.error(request, f"Order #{order_id} does not exist.")
        else:
            messages.error(request, "Customer profile not found.")
        return redirect('orders:customer_past_transactions')
    
    ordered_items = order.ordereditem_set.all()
    
    context = {
        'order': order,
        'ordered_items': ordered_items,
    }
    return render(request, 'orders/past_transactions.html', context)


@login_required
def checkout(request):
    user = request.user
    
    try:
        customer = user.customer
    except Customer.DoesNotExist:
        messages.error(request, "Your customer profile is incomplete. Please update it.")
        # Ensure 'customer_profile' is the correct URL name
        return redirect('customer_profile') 

    # --- CRITICAL ENFORCEMENT CHECK ---
    if customer.delivery_location is None:
        messages.error(request, 
            "🛑 **Action Required:** Please select your **Delivery Region (Fee Zone)** in your profile to calculate the mandatory Delivery Fee."
        )
        # Redirect to the profile update view
        return redirect('customer_profile') 
        
    # --- IF REGION IS SET, PROCEED ---

    # 1. Fetch the correct delivery fee
    delivery_fee = customer.delivery_location.fee
    
    # 2. Update the current Order object's delivery_fee and grand_total
    try:
        current_order = Order.objects.get(customer=customer, finalized=False)
        current_order.delivery_fee = delivery_fee # Use the fee from the selected region
        
        # Recalculate grand_total based on the new delivery fee
        current_order.grand_total = current_order.subtotal + current_order.delivery_fee
        current_order.save() 
        
    except Order.DoesNotExist:
        messages.error(request, "No active order found. Please place items in your cart first.")
        return redirect('orders:menu') # Redirect back to the menu

    # 3. Proceed to payment initiation or final checkout page
    context = {
        'order': current_order,
        'delivery_fee': delivery_fee,
        # ... other context variables ...
    }
    
    # Replace this with your actual next step (e.g., render the checkout page or redirect to payment)
    return render(request, 'orders/checkout.html', context)

@login_required
def payment(request, order_id):
    """Display payment page and initiate payment processing"""
    order = get_object_or_404(Order, id=order_id, customer=request.user.customer)
    
    # Your payment integration logic here
    # This could be Paystack, Flutterwave, etc.
    
    context = {
        'order': order,
        'payment_key': 'your_payment_key_here',  # From your payment gateway
        'email': request.user.email,
        'amount': int(order.grand_total * 100),  # Amount in kobo
    }
    
    return render(request, 'orders/payment.html', context)

@staff_member_required
def update_stock(request):
    staff = request.user.staff
    if staff.designation not in ['CS', 'KS', 'MG', 'MD']:
        messages.error(request, 'You do not have permission to update stock.')
        return redirect('staff_dashboard')

    if request.method == 'POST':
        print("Updating stock levels...")
        
        # Update Individual Items
        items_updated = 0
        for item in Item.objects.all():
            try:
                stock_key = f'item_{item.id}'
                new_stock = int(request.POST.get(stock_key, item.stock))
                if new_stock >= 0 and new_stock != item.stock:
                    item.stock = new_stock
                    item.save()
                    items_updated += 1
                    print(f"Updated {item.name} stock to {new_stock}")
            except (ValueError, TypeError) as e:
                print(f"Error updating {item.name}: {e}")
                continue
        
        # Update Combos
        combos_updated = 0
        for combo in Combo.objects.all():
            try:
                combo_key = f'combo_{combo.id}'
                new_stock = int(request.POST.get(combo_key, combo.stock))
                if new_stock >= 0 and new_stock != combo.stock:
                    combo.stock = new_stock
                    combo.save()
                    combos_updated += 1
                    print(f"Updated {combo.name} stock to {new_stock}")
            except (ValueError, TypeError) as e:
                print(f"Error updating {combo.name}: {e}")
                continue
                        
        messages.success(request, f'Stock levels updated successfully! {items_updated} items and {combos_updated} combos modified.')
        return redirect('orders:update_stock')

    items = Item.objects.all()
    combos = Combo.objects.all()
    
    # Calculate low stock items (less than 10)
    items_low_stock = items.filter(stock__lt=10).count()
    combos_low_stock = combos.filter(stock__lt=10).count()

    context = {
        'items': items,
        'combos': combos,
        'staff': staff,
        'items_low_stock': items_low_stock,
        'combos_low_stock': combos_low_stock,
    }
    
    return render(request, 'orders/update_stock.html', context)

# Admin Controls
@login_required
@staff_member_required
def generate_sales(request):
    staff = get_object_or_404(Staff, user=request.user)
    if staff.designation not in ['CS', 'KS', 'DL', 'AC', 'AD', 'MG', 'MD']:
        messages.error(request, 'You do not have permission to generate sales reports.')
        return redirect('staff_dashboard')

    today = date.today().strftime("%d%m%Y")

    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = "attachment; filename=Sales_"+str(today)+".xlsx"

    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet("Sales_"+str(today))

    #Writing the headers
    row = 0
    font_style = xlwt.XFStyle()
    font_style.font.bold = True
    columns = [
        'Category', 'Item ID', 'Item Name', 'Orders', 'Sales',
    ]

    for col in range(len(columns)):
        ws.write(row, col, columns[col], font_style)

    #Writing Orders data to the sheet
    font_style = xlwt.XFStyle()

    orders = Order.objects.filter(date_placed=date.today(), finalized = True)
    items = Item.objects.all()
    ordered_items = []

    for order in orders:
        ordered_items += OrderedItem.objects.filter(order = order)

    net_sales = 0
    for c in range(len(CATEGORIES)):
        category = str(CATEGORIES[c][0])
        for i in items:
            if i.category == category:

                count = 0
                sales = 0

                for o_item in ordered_items:
                    if o_item.item == i:
                        count += o_item.quantity
                        sales += o_item.price

                net_sales += sales

                row += 1
                ws.write(row, 0, i.category, font_style)
                ws.write(row, 1, i.id, font_style)
                ws.write(row, 2, i.name, font_style)
                ws.write(row, 3, count, font_style)
                ws.write(row, 4, sales, font_style)

    row += 1
    ws.write(row, 3, "TOTAL SALES", font_style)
    ws.write(row, 4, net_sales, font_style)

    wb.save(response)

    return response

@login_required
@staff_member_required
def notify_offers(request):

    customers = Customer.objects.all()

    if request.method=="POST":

        form = OfferForm(request.POST)
        if form.is_valid():

            offer_text = form.cleaned_data['offer_text']

            mail_customers(customers, offer_text)

            messages.success(request, 'Order Published!')

            return redirect('staff_dashboard')

    else:
        form = OfferForm()

    context = {
        'form' : form
    }

    return render(request, 'orders/notify_offers.html', context)

@login_required
@staff_member_required
def monthly_report(request):
    """Monthly sales report with month selection for auditing"""
    
    # Get month parameter (now in format 'YYYY-MM')
    month_param = request.GET.get('month', '')
    today = date.today()
    
    # Parse the month parameter
    if month_param and '-' in month_param:
        try:
            # Split '2025-09' into year and month
            year_str, month_str = month_param.split('-')
            report_year = int(year_str)
            report_month = int(month_str)
        except (ValueError, IndexError):
            # Fallback to current month if parsing fails
            report_month = today.month
            report_year = today.year
    else:
        # Fallback to current month
        report_month = today.month
        report_year = today.year
    
    # Validate month and year
    if report_month < 1 or report_month > 12:
        report_month = today.month
    if report_year < 2020 or report_year > today.year + 1:
        report_year = today.year
    
    # Calculate start and end date of the requested month
    _, num_days = monthrange(report_year, report_month)
    start_date = date(report_year, report_month, 1)
    end_date = date(report_year, report_month, num_days)
    
    # Get ALL orders for the month (finalized and non-finalized for complete audit)
    monthly_orders = Order.objects.filter(
        date_placed__gte=start_date,
        date_placed__lte=end_date
    ).select_related('customer__user').order_by('date_placed', 'time_placed')
    
    # Calculate comprehensive statistics
    total_orders = monthly_orders.count()
    finalized_orders = monthly_orders.filter(finalized=True)
    delivered_orders = finalized_orders.filter(delivered=True)
    
    # Revenue calculations
    total_revenue = finalized_orders.aggregate(
        total=Sum('grand_total')
    )['total'] or Decimal('0.00')
    
    pending_revenue = monthly_orders.filter(
        finalized=False
    ).aggregate(
        total=Sum('grand_total')
    )['total'] or Decimal('0.00')
    
    # Daily breakdown with complete data
    daily_report_data = {}
    
    for order in monthly_orders:
        day_key = order.date_placed.strftime('%Y-%m-%d')
        
        if day_key not in daily_report_data:
            daily_report_data[day_key] = {
                'date': order.date_placed,
                'orders_count': 0,
                'finalized_orders': 0,
                'delivered_orders': 0,
                'revenue': Decimal('0.00'),
                'pending_revenue': Decimal('0.00'),
                'events': [],
            }

        # Update day totals
        daily_report_data[day_key]['orders_count'] += 1
        
        if order.finalized:
            daily_report_data[day_key]['finalized_orders'] += 1
            daily_report_data[day_key]['revenue'] += order.grand_total
            
            if order.delivered:
                daily_report_data[day_key]['delivered_orders'] += 1
        else:
            daily_report_data[day_key]['pending_revenue'] += order.grand_total
        
        # Add order event
        status = "Pending Payment"
        if order.finalized:
            status = "Delivered" if order.delivered else "Processing"
        
        daily_report_data[day_key]['events'].append({
            'order_id': order.id,
            'time': order.time_placed.strftime('%I:%M %p') if order.time_placed else 'N/A',
            'customer': order.customer.name,
            'total': order.grand_total,
            'status': status,
            'finalized': order.finalized,
            'delivered': order.delivered,
            'payment_ref': order.payment_reference or 'No Payment',
        })
    
    # Calculate additional metrics
    business_days = len(daily_report_data)
    average_daily_revenue = total_revenue / business_days if business_days > 0 else Decimal('0.00')
    average_order_value = total_revenue / finalized_orders.count() if finalized_orders.count() > 0 else Decimal('0.00')
    delivery_rate = (delivered_orders.count() / finalized_orders.count() * 100) if finalized_orders.count() > 0 else 0
    
    # Generate month choices for dropdown (format: 'YYYY-MM')
    months = []
    current_year = today.year
    current_month = today.month
    
    # Generate 24 months back from current month
    for i in range(24):
        # Calculate year and month
        months_back = i
        year = current_year - (months_back // 12)
        month = current_month - (months_back % 12)
        
        if month <= 0:
            month += 12
            year -= 1
        
        # Skip future months
        if year > current_year or (year == current_year and month > current_month):
            continue
            
        month_value = f"{year}-{month:02d}"
        month_label = f"{date(year, month, 1).strftime('%B %Y')}"
        
        months.append({
            'value': month_value,
            'label': month_label
        })
    
    # Sort months chronologically (newest first)
    months.sort(key=lambda x: x['value'], reverse=True)
    
    context = {
        'report_month': start_date.strftime('%B'),
        'report_year': report_year,
        'report_month_num': report_month,
        'daily_reports': sorted(daily_report_data.values(), key=lambda x: x['date']),
        'total_orders': total_orders,
        'finalized_orders': finalized_orders.count(),
        'delivered_orders': delivered_orders.count(),
        'total_revenue': total_revenue,
        'pending_revenue': pending_revenue,
        'start_date': start_date,
        'end_date': end_date,
        'business_days': business_days,
        'average_daily_revenue': average_daily_revenue,
        'average_order_value': average_order_value,
        'delivery_rate': delivery_rate,
        'month_choices': months,
        'selected_month': f"{report_year}-{report_month:02d}",
        'today': today,
    }
    
    return render(request, 'orders/monthly_report.html', context)

@staff_member_required
def day_orders(request):
    """View for TODAY'S operational orders (staff focus)"""
    staff = get_object_or_404(Staff, user=request.user)
    
    if staff.designation not in ['MD', 'MG', 'CS', 'KS', 'DL']:
        messages.error(request, 'You do not have permission to view today\'s orders.')
        return redirect('staff_dashboard')
    
    # Get TODAY'S orders only
    today = datetime.now().date()
    today_orders = Order.objects.filter(
        date_placed=today,
        finalized=True
    ).select_related('customer').order_by('-time_placed')
    
    # Get counts instead of QuerySets
    pending_orders_count = today_orders.filter(delivered=False).count()
    delivered_orders_count = today_orders.filter(delivered=True).count()
    total_orders_count = today_orders.count()
    
    # Calculate revenue
    revenue_sum = today_orders.aggregate(Sum('grand_total'))['grand_total__sum']
    total_revenue = revenue_sum if revenue_sum is not None else Decimal('0.00')
    
    context = {
        'staff': staff,
        'today_orders': today_orders,
        'pending_orders_count': pending_orders_count,
        'delivered_orders_count': delivered_orders_count,
        'total_orders_count': total_orders_count,
        'today_date': today,
        'total_revenue': total_revenue,
    }
    return render(request, 'orders/day_orders.html', context)

@login_required
def order_details_ajax(request):
    """AJAX view to get order details for the modal - works for both customers and staff"""
    if request.method == 'GET':
        order_id = request.GET.get('order_id')
        
        try:
            order = Order.objects.get(id=order_id)
            ordered_items = OrderedItem.objects.filter(order=order)
            
            # Check permissions - staff can see any order, customers only their own
            if request.user.is_staff:
                # Staff can view any order
                pass
            else:
                # Regular users can only view their own orders
                customer = get_object_or_404(Customer, user=request.user)
                if order.customer != customer:
                    return JsonResponse({
                        'success': False,
                        'error': 'You do not have permission to view this order.'
                    })
            
            # Render the order details HTML
            html = render_to_string('orders/_order_details.html', {
                'order': order,
                'ordered_items': ordered_items,
                'is_staff': request.user.is_staff,  # Pass staff status to template
            })
            
            return JsonResponse({
                'success': True,
                'html': html
            })
        except Order.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Order not found'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid request'
    })

# Update the staff_dashboard view to include pending orders in context
@staff_member_required
def staff_dashboard(request):
    user = request.user
    
    # Staff object creation/lookup logic
    if not Staff.objects.filter(user=user).exists():
        staff = Staff.objects.create(
            user=user,
            name=user.username,
            email=user.email,
            designation='AD' 
        )
    else:
        staff = get_object_or_404(Staff, user=user)
    
    # Get pending orders based on staff designation
    if staff.designation in ['CS', 'AD', 'MD', 'KS', 'DL']:
        pending_orders = Order.objects.filter(finalized=True, delivered=False).order_by('date_placed', 'time_placed')
        pending_orders_count = pending_orders.count()
        
        # Calculate pending orders total revenue
        pending_revenue_sum = pending_orders.aggregate(Sum('grand_total'))['grand_total__sum']
        pending_orders_total = pending_revenue_sum if pending_revenue_sum is not None else Decimal('0.00')
        
        # Add this line - since all pending orders need to be delivered
        to_be_delivered_count = pending_orders_count
    else:
        pending_orders = Order.objects.none()
        pending_orders_count = 0
        pending_orders_total = Decimal('0.00')
        to_be_delivered_count = 0
    
    # Render the initial dashboard template
    return render(request, 'users/staff_dashboard.html', {
        'staff': staff,
        'pending_orders': pending_orders,
        'pending_orders_count': pending_orders_count,
        'pending_orders_total': pending_orders_total,
        'to_be_delivered_count': to_be_delivered_count,  # Add this
    })

@login_required
@staff_member_required
def staff_order_details(request, order_id):
    """View for staff to see order details (without customer restriction)"""
    staff = get_object_or_404(Staff, user=request.user)
    
    # Check if staff has permission to view orders
    if staff.designation not in ['CS', 'KS', 'DL', 'MG', 'MD', 'AD']:
        messages.error(request, 'You do not have permission to view order details.')
        return redirect('staff_dashboard')
    
    # 1. Efficiently get the order and its related customer
    try:
        # Use select_related to fetch the customer in the same query
        order = Order.objects.select_related('customer').get(id=order_id)
    except Order.DoesNotExist:
        messages.error(request, f'Order #{order_id} not found.')
        return redirect('staff_dashboard')
    
    # 2. Get the ordered items
    ordered_items = OrderedItem.objects.filter(order=order)

    # 3. Compile context and render the template
    context = {
        'order': order,
        'ordered_items': ordered_items, # Ensure you pass this to the template
        'staff': staff,
    }

    # Assuming your template is named 'orders/staff_order_details.html'
    return render(request, 'orders/staff_order_details.html', context)

    def is_managing_director(user):
        return user.is_authenticated and (user.is_superuser or user.groups.filter(name='Managing Director').exists())

@user_passes_test(is_managing_director)
def customer_management(request):
    customers = Customer.objects.select_related('user').all().order_by('user__first_name')
    
    context = {
        'customers': customers,
        'total_customers': customers.count(),
    }
    return render(request, 'orders/customer_management.html', context)

@user_passes_test(is_managing_director)
def export_customers_csv(request):
    """Export customer contacts ranked by total spending"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customer_contacts_ranked.csv"'
    
    writer = csv.writer(response)
    # Write CSV header
    writer.writerow([
        'Rank',
        'Customer Name', 
        'Email', 
        'Phone Number', 
        'Registration Date',
        'Total Orders', 
        'Total Spent (₦)',
        'Average Order Value (₦)',
        'Customer Tier',
        'Last Order Date',
        'Days Since Last Order',
        'Delivery Location'
    ])
    
    customers = Customer.objects.select_related('user').prefetch_related('order_set').all()
    
    # Calculate customer data with rankings
    customer_data = []
    for customer in customers:
        customer_orders = customer.order_set.filter(finalized=True)
        total_orders = customer_orders.count()
        total_spent = sum(order.grand_total for order in customer_orders if order.grand_total)
        avg_order_value = total_spent / total_orders if total_orders > 0 else 0
        last_order = customer_orders.order_by('-date_placed').first()
        
        # Calculate days since last order
        if last_order:
            days_since_last = (date.today() - last_order.date_placed).days
        else:
            days_since_last = 999  # Large number for customers with no orders
        
        customer_data.append({
            'customer': customer,
            'total_orders': total_orders,
            'total_spent': total_spent,
            'avg_order_value': avg_order_value,
            'last_order_date': last_order.date_placed if last_order else 'Never',
            'days_since_last': days_since_last,
        })
    
    # Sort by total spent (primary) and recency (secondary)
    customer_data.sort(key=lambda x: (-x['total_spent'], -x['days_since_last']))
    
    # Write ranked customer data
    for rank, data in enumerate(customer_data, 1):
        customer = data['customer']
        
        # Determine customer tier based on spending
        if data['total_orders'] == 0:
            customer_tier = 'New Customer'
        elif data['total_spent'] > 50000:
            customer_tier = 'VIP'
        elif data['total_spent'] > 20000:
            customer_tier = 'Gold'
        elif data['total_spent'] > 10000:
            customer_tier = 'Silver'
        elif data['total_spent'] > 5000:
            customer_tier = 'Bronze'
        else:
            customer_tier = 'Standard'
        
        writer.writerow([
            rank,  # Ranking
            f"{customer.user.first_name} {customer.user.last_name}".strip() or customer.name,
            customer.user.email,
            customer.phone or 'Not provided',
            customer.user.date_joined.strftime('%Y-%m-%d'),
            data['total_orders'],
            f"{data['total_spent']:.2f}",
            f"{data['avg_order_value']:.2f}",
            customer_tier,
            data['last_order_date'],
            data['days_since_last'] if data['last_order_date'] != 'Never' else 'N/A',
            customer.delivery_location.name if customer.delivery_location else 'Not set'
        ])
    
    return response

@user_passes_test(is_managing_director)
def customer_analytics(request):
    # Basic analytics
    total_customers = Customer.objects.count()
    customers_with_phone = Customer.objects.exclude(phone__isnull=True).exclude(phone='').count()
    new_customers_this_month = Customer.objects.filter(
        user__date_joined__month=datetime.now().month,
        user__date_joined__year=datetime.now().year
    ).count()
    
    # Top customers by orders - FIX: Use grand_total instead of total_price
    top_customers = Customer.objects.annotate(
        order_count=Count('order'),
        total_spent=Sum('order__grand_total')  # Changed from total_price
    ).order_by('-total_spent')[:10]
    
    context = {
        'total_customers': total_customers,
        'customers_with_phone': customers_with_phone,
        'phone_percentage': (customers_with_phone / total_customers * 100) if total_customers else 0,
        'new_customers_this_month': new_customers_this_month,
        'top_customers': top_customers,
    }
    return render(request, 'orders/customer_analytics.html', context)

@user_passes_test(is_managing_director)
def export_analytics_csv(request):
    """Export customer analytics and behavior data"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customer_analytics.csv"'
    
    writer = csv.writer(response)
    # Write CSV header for analytics
    writer.writerow([
        'Customer Name',
        'Email', 
        'Join Date',
        'Customer Age (Days)',
        'Total Orders',
        'Total Revenue (₦)',
        'Avg Order Value (₦)',
        'Order Frequency (Days)',
        'Customer Lifetime Value',
        'Preferred Category',
        'Loyalty Points',
        'Last Activity',
        'Status'
    ])
    
    customers = Customer.objects.select_related('user').prefetch_related('order_set').all()
    
    customer_analytics = []
    for customer in customers:
        customer_orders = customer.order_set.filter(finalized=True).order_by('date_placed')
        total_orders = customer_orders.count()
        total_spent = sum(order.grand_total for order in customer_orders if order.grand_total)
        
        # Calculate customer metrics
        customer_age = (date.today() - customer.user.date_joined.date()).days
        avg_order_value = total_spent / total_orders if total_orders > 0 else 0
        
        # Calculate order frequency
        if total_orders > 1:
            first_order = customer_orders.first().date_placed
            last_order = customer_orders.last().date_placed
            order_frequency = (last_order - first_order).days / total_orders
        else:
            order_frequency = 0
        
        # Determine customer status
        if total_orders == 0:
            status = 'Inactive'
        elif customer_age < 30:
            status = 'New'
        elif order_frequency < 7:
            status = 'Frequent'
        elif order_frequency < 30:
            status = 'Regular'
        else:
            status = 'Occasional'
        
        customer_analytics.append({
            'customer': customer,
            'total_orders': total_orders,
            'total_spent': total_spent,
            'customer_age': customer_age,
            'avg_order_value': avg_order_value,
            'order_frequency': order_frequency,
            'status': status,
        })
    
    # Sort by customer lifetime value (total spent)
    customer_analytics.sort(key=lambda x: x['total_spent'], reverse=True)
    
    for data in customer_analytics:
        customer = data['customer']
        
        writer.writerow([
            f"{customer.user.first_name} {customer.user.last_name}".strip() or customer.name,
            customer.user.email,
            customer.user.date_joined.strftime('%Y-%m-%d'),
            data['customer_age'],
            data['total_orders'],
            f"{data['total_spent']:.2f}",
            f"{data['avg_order_value']:.2f}",
            f"{data['order_frequency']:.1f}",
            f"{data['total_spent']:.2f}",  # Simple CLV
            'General',  # You can enhance this with actual category analysis
            customer.loyalty_points,
            'Active' if data['total_orders'] > 0 else 'Inactive',
            data['status']
        ])
    
    return response

@staff_member_required
def all_transactions(request):
    """View all finalized transactions across all time"""
    # Get all finalized orders, ordered by most recent first
    all_orders = Order.objects.filter(finalized=True).select_related('customer__user').order_by('-date_placed', '-time_placed')
    
    # Calculate statistics
    total_orders = all_orders.count()
    total_revenue = all_orders.aggregate(total=Sum('grand_total'))['total'] or Decimal('0.00')
    delivered_orders = all_orders.filter(delivered=True).count()
    pending_orders = all_orders.filter(delivered=False).count()
    
    # Pagination
    paginator = Paginator(all_orders, 50)  # 50 orders per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'orders': page_obj,
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'delivered_orders': delivered_orders,
        'pending_orders': pending_orders,
    }
    return render(request, 'orders/all_transactions.html', context)

@staff_member_required
def daily_report(request):
    """Daily sales and order report for a specific date"""
    # Get the date from request parameters, default to today
    report_date_str = request.GET.get('date')
    if report_date_str:
        try:
            report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            report_date = date.today()
    else:
        report_date = date.today()
    
    # Get orders for the specific date
    daily_orders = Order.objects.filter(
        date_placed=report_date,
        finalized=True
    ).select_related('customer__user').order_by('time_placed')
    
    # Calculate daily statistics
    total_orders = daily_orders.count()
    total_revenue = daily_orders.aggregate(total=Sum('grand_total'))['total'] or Decimal('0.00')
    delivered_orders = daily_orders.filter(delivered=True).count()
    average_order_value = total_revenue / total_orders if total_orders > 0 else Decimal('0.00')
    
    # Get top selling items for the day
    ordered_items = OrderedItem.objects.filter(
        order__date_placed=report_date,
        order__finalized=True
    )
    
    # Item sales breakdown
    item_sales = {}
    for item in ordered_items:
        if item.item:
            item_name = item.item.name
        elif item.combo:
            item_name = f"🎁 {item.combo.name}"
        else:
            continue
            
        if item_name not in item_sales:
            item_sales[item_name] = {'quantity': 0, 'revenue': Decimal('0.00')}
        
        item_sales[item_name]['quantity'] += item.quantity
        item_sales[item_name]['revenue'] += item.price
    
    # Sort by revenue
    top_items = sorted(item_sales.items(), key=lambda x: x[1]['revenue'], reverse=True)[:10]
    
    context = {
        'report_date': report_date,
        'daily_orders': daily_orders,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'delivered_orders': delivered_orders,
        'average_order_value': average_order_value,
        'top_items': top_items,
        'prev_date': report_date - timedelta(days=1),
        'next_date': report_date + timedelta(days=1),
    }
    return render(request, 'orders/daily_report.html', context)

@user_passes_test(is_managing_director)
def mg_dashboard(request):
    return render(request, 'orders/mg_dashboard.html')