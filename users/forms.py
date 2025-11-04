from django import forms 
from users.models import Customer, Staff
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from orders.models import DeliveryLocation

class UserRegistrationForm(UserCreationForm):
    
    class Meta(UserCreationForm):
        model = User
        fields = ['username', 'email', 'password1', 'password2']
            
class CustomerProfileForm(forms.ModelForm):
    
    # 1. Define the mandatory ModelChoiceField for Delivery Region
    delivery_location = forms.ModelChoiceField(
        queryset=DeliveryLocation.objects.filter(is_active=True).order_by('fee'),
        label='Select Delivery Region (Fee Zone)',
        required=True, # ENFORCES selection
        help_text="Required: This choice determines your fixed delivery fee. You must select a region to proceed."
    )
    
    class Meta:
        model = Customer
        # 2. CRITICAL: Add delivery_location to the fields list
        fields = ['name', 'address', 'phone', 'image', 'delivery_location']
        # 2. CRITICAL: Add the widgets dictionary to shrink the address box
        widgets = {
            'address': forms.Textarea(attrs={'rows': 1, 'placeholder': 'Enter your full street address or landmark'}),
        }


class StaffProfileForm(forms.ModelForm):
    class Meta:
        model = Staff
        fields = ['name', 'phone', 'image']
        
