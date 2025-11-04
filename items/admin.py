from django.contrib import admin
from items.models import Item, Combo

admin.site.register([Item])

# Register your models here.
class ComboAdmin(admin.ModelAdmin):
    # These fields will be displayed in the change list view (table)
    list_display = ('name', 'rate', 'item1', 'item2', 'item3', 'item4', 'item5')
    
    # 🛑 CRITICAL FIX: Hide the 'rate' field from the input form
    exclude = ('rate',) 
    
    # Optional: Display the fields in a specific order
    fields = (
        'name', 'description', 'image',
        ('item1', 'item2'),
        ('item3', 'item4', 'item5'),
    )
    
    # Optional: Display calculated rate in read-only format in the detail view
    readonly_fields = ('calculated_rate_display',)

    def calculated_rate_display(self, obj):
        # Use the calculation logic for display purposes in Admin detail view
        return f'₦{obj.calculate_rate():,.2f}'
    calculated_rate_display.short_description = 'Calculated Price (5% Off)'

admin.site.register(Combo, ComboAdmin)