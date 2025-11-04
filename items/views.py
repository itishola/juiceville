from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required # Required for proper login check
from django.contrib import messages

from users.models import Staff 
from items.models import Item, Combo
from items.forms import ItemForm, ComboForm

from orders.forms import OfferForm
from orders.models import Order, OrderedItem
from users.models import Customer

# --- UTILITY FUNCTION FOR PERMISSION CHECK ---
def check_mg_md_permission(request):
    """Fetches Staff object and returns it if designation is 'MD' or 'MG', 
    or redirects and returns None otherwise."""
    # Superuser bypasses the designation check
    if request.user.is_superuser:
        # Return a placeholder object for superusers to proceed
        return True 

    # Fetch the staff object for designation check
    staff = get_object_or_404(Staff, user=request.user)
    
    if staff.designation not in ['MD', 'MG']:
        messages.error(request, 'Access denied. Only Managing Director (MD) and Manager (MG) staff can perform this action.')
        return redirect('staff_dashboard')
    return staff


@login_required
@staff_member_required
def create_item(request):
    # MD/MG/Superuser ACCESS CHECK
    check = check_mg_md_permission(request)
    if check is not True and not isinstance(check, Staff):
        return check

    if request.method == "POST":
        form = ItemForm(request.POST, request.FILES)
        if form.is_valid():
            
            form.save()
            messages.success(request, f'Item Added to Menu!')
            
            # FIX: Redirect to a non-order-related URL, like the Home page ('index')
            # You may need to use a namespace if 'index' is not global (e.g., 'app_name:index')
            return redirect('index') 
        
    else:
        form = ItemForm()
        
    context = {
        'form' : form
    }
    return render(request, 'items/create_item.html', context)
        
@login_required
@staff_member_required
def update_item(request, pk):
    # MD/MG/Superuser ACCESS CHECK
    check = check_mg_md_permission(request)
    if check is not True and not isinstance(check, Staff):
        return check
    
    item = get_object_or_404(Item, pk = pk)
    
    if request.method == "POST":
        # Note: Added request.FILES to ItemForm for image handling consistency
        form = ItemForm(request.POST, request.FILES, instance = item)
        if form.is_valid():
            
            form.save()
            messages.success(request, f'Item Updated!')
            
            return redirect('items:menu')
        
    else:
        form = ItemForm(instance = item)
        
    context = {
        'form' : form,
        'item' : item
    }
    return render(request, 'items/update_item.html', context)

def create_combo(request):
    # MD/MG/Superuser ACCESS CHECK
    check = check_mg_md_permission(request)
    if check is not True and not isinstance(check, Staff):
        return check
    
    if request.method == "POST":
        form = ComboForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, f'Combo Created!')
            
            # 1. Option 1: Redirect to the CORRECT namespaced URL (If redirecting to itself)
            # return redirect('items:create_combo') 
            
            # 2. Option 2: Redirect to a staff dashboard or home page (RECOMMENDED)
            return redirect('index') # Or 'orders:staff_dashboard', etc.
        
    # If the form is NOT valid, the error often happens here if you're returning 
    # the form with errors, and a template link is causing the reverse match failure.

    else:
        form = ComboForm()
        
    context = {
        'form' : form
    }
    return render(request, 'items/create_combo.html', context)

@login_required
@staff_member_required
def update_combo(request, pk):
    # MD/MG/Superuser ACCESS CHECK
    check = check_mg_md_permission(request)
    if check is not True and not isinstance(check, Staff):
        return check
    
    combo = get_object_or_404(Combo, pk = pk)
    
    if request.method == "POST":
        form = ComboForm(request.POST, instance = combo)
        if form.is_valid():
            
            form.save()
            messages.success(request, f'Combo Updated Successfully!')
            return redirect('create_combo')
        
    else:
        form = ComboForm(instance = combo)
        
    context = {
        'form' : form,
        'combo' : combo
    }
    return render(request, 'items/create_combo.html', context)

# --- VIEW FOR NOTIFY OFFERS ---
# Note: This view assumes it is defined in /item/views.py for this solution, 
# but it may be better suited for an orders/views.py file.
@login_required
@staff_member_required
def notify_offers(request):
    # MD/MG/Superuser ACCESS CHECK
    check = check_mg_md_permission(request)
    if check is not True and not isinstance(check, Staff):
        return check

    if request.method=="POST":
        form = OfferForm(request.POST)
        if form.is_valid():
            # mail_customers logic goes here
            messages.success(request, 'Offer Published to Customers!')
            return redirect('staff_dashboard') 
    else:
        form = OfferForm()

    context = {
        'form' : form
    }
    return render(request, 'orders/notify_offers.html', context)

def menu_view(request):
    current_order = None
    if request.user.is_authenticated:
        try:
            # FIX: Use 'finalized=False' (or 'delivered=False')
            # to find the active order (the user's open cart).
            current_order = Order.objects.get(customer=request.user, finalized=False)
            
        except Order.DoesNotExist:
            pass
        
    context = {
        # ... other context data (menu_items) ...
        'order': current_order,  # <-- CRITICAL: Pass the object here
    }
    return render(request, 'orders/menu.html', context)

def optimize_image(image_path, max_size=(800, 800), quality=85):
    """Optimize image for web/mobile"""
    with Image.open(image_path) as img:
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, '#FFFFFF')
            background.paste(img, mask=img.split()[-1])
            img = background
        
        # Convert to WebP for better compression
        output_path = os.path.splitext(image_path)[0] + '.webp'
        img.save(output_path, 'WEBP', quality=quality, optimize=True)
        return output_path