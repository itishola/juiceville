from django.contrib import admin
from django import forms
from orders.models import Order, OrderedItem, DeliveryLocation, OperatingHours

admin.site.register([Order, OrderedItem,]) 

@admin.register(DeliveryLocation)
class DeliveryLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'fee', 'is_active') 
    list_editable = ('fee', 'is_active') 

# Register your models here.

class OperatingHoursAdminForm(forms.ModelForm):
    class Meta:
        model = OperatingHours
        fields = '__all__'
        widgets = {
            'opening_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
            'closing_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
        }

@admin.register(OperatingHours)
class OperatingHoursAdmin(admin.ModelAdmin):
    # Link the custom form to the ModelAdmin
    form = OperatingHoursAdminForm 
    
    list_display = ('get_day_display', 'closed_date', 'is_open', 'opening_time', 'closing_time')
    list_filter = ('day', 'is_open')
    
    # Custom fieldsets for better organization
    fieldsets = (
        (None, {
            'fields': ('day', 'closed_date', 'is_open'),
        }),
        ('Time Window', {
            'fields': ('opening_time', 'closing_time'),
            'description': 'Set precise opening and closing times.'
        }),
    )