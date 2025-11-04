from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, authenticate
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from orders.models import Order

from users.models import Customer, Staff
from users.forms import UserRegistrationForm, CustomerProfileForm, StaffProfileForm


def post_login(request):
    if request.user.is_staff:
        return redirect('staff_dashboard')
    else:
        return redirect('customer_dashboard')

def register_customer(request):
    """
    Renders the registration page, which now only contains social login buttons.
    Manual registration forms are no longer processed.
    """
    return render(request, 'users/register_customer.html', {})

@login_required
def customer_dashboard(request):
    
    user = request.user
    if not user.is_superuser:
        if not Customer.objects.filter(user = user).exists():
            
            customer = Customer.objects.create(
                user = user,
            )
            customer.save()
            messages.success(request, f'Please Update Your Profile to Help us serve You Better!')
            
            return redirect('customer_profile')

        else:
            customer = get_object_or_404(Customer, user = user)
        
        if customer.name == "" or customer.address == "" or customer.phone == "":
            messages.success(request, f'Please Update Your Profile to Help us serve You Better!')
            return redirect('customer_profile')
        
        context = {
            'customer' : customer
        }
        
        return render(request, 'users/customer_dashboard.html', context)
   
@login_required 
def customer_profile(request):
    
    customer = get_object_or_404(Customer, user = request.user)
    
    if request.method == "POST":
        
        # This line passes the new delivery_location data from the form
        form = CustomerProfileForm(request.POST, request.FILES, instance = customer) 
        
        if form.is_valid():
            # This line saves all fields defined in form.Meta.fields, including delivery_location
            form.save() 
            
            # The rest of your logic is correct for synchronization
            customer.email = request.user.email
            customer.save()
            
            messages.success(request, f'Profile Updated!')
            return redirect('customer_dashboard')
        
    else:
        form = CustomerProfileForm(instance = customer)
    
    context = {
        'customer' : customer,
        'form' : form
    }
    
    # Assuming this renders your profile template
    return render(request, 'users/customer_profile.html', context)

####
# Staff Methods

@staff_member_required
def register_staff(request):
    
    if request.method == "POST":
        user_form = UserRegistrationForm(request.POST)
        staff_form = StaffProfileForm(request.POST, request.FILES)
        
        if user_form.is_valid() and staff_form.is_valid():
            user_form.save()

            user = user_form.instance
            user.is_superuser = True
            user.is_staff = True
            user.save()
            
            staff = staff_form.instance         
            staff.user = user
            staff.email = user.email
            staff.save()
            
            return redirect('staff_dashboard')
    else:
        user_form = UserRegistrationForm()
        staff_form = StaffProfileForm()
    
    context = {
        'uform' : user_form,
        'cform' : staff_form
    }
    
    return render(request, 'users/register_staff.html', context)

@staff_member_required
def staff_dashboard(request):
    
    user = request.user
    
    # Check if a Staff object exists for the user; if not, create one.
    if not Staff.objects.filter(user=user).exists():
        
        # CRITICAL FIX: Add default/placeholder values for required fields (emp_id, phone)
        staff = Staff.objects.create(
            user=user,
            name=user.username,
            email=user.email,
            emp_id='000',  
            phone='00000000000',
            # Assign a default designation
            designation='AD' 
        )
    else:
        staff = get_object_or_404(Staff, user=user)

    # The original logic (from the helper function):
    if staff.designation in ['CS', 'KS', 'DL', 'AD', 'MG', 'MD']:
        pending_orders = Order.objects.filter(finalized=True, delivered=False)
    elif staff.designation == 'KS':
        pending_orders = Order.objects.filter(finalized=True, delivered=False) # Redundant
    elif staff.designation == 'DL':
        pending_orders = Order.objects.filter(finalized=True, delivered=False) # Redundant
    else:
        pending_orders = Order.objects.none()

    context = {
        'staff' : staff,
        'pending_orders': pending_orders
    }
    
    return render(request, 'users/staff_dashboard.html', context)
      
@staff_member_required  
def staff_profile(request):
    
    staff = get_object_or_404(Staff, user = request.user)
    
    if request.method == "POST":
        
        form = StaffProfileForm(request.POST, request.FILES, instance = staff)
        
        if form.is_valid():
            form.save()
            staff.email = request.user.email
            staff.save()
            
            return redirect('staff_dashboard')
        
    else:
        form = StaffProfileForm(instance = staff)
    
    context = {
        'staff' : staff,
        'form' : form
    }    
    
    return render(request, 'users/staff_profile.html', context)

@staff_member_required
def staff_management(request):
    """Staff management view"""
    staff_members = Staff.objects.all().select_related('user').order_by('designation', 'name')
    
    # Calculate statistics
    total_staff = staff_members.count()
    active_staff = staff_members.filter(user__is_active=True).count()
    managers_count = staff_members.filter(designation__in=['MD', 'MG']).count()
    kitchen_staff_count = staff_members.filter(designation='KS').count()
    
    context = {
        'staff_members': staff_members,
        'total_staff': total_staff,
        'active_staff': active_staff,
        'managers_count': managers_count,
        'kitchen_staff_count': kitchen_staff_count,
    }
    return render(request, 'users/staff_management.html', context)