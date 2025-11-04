# orders/models.py

from django.db import models
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.conf import settings
from decimal import Decimal
from datetime import datetime, time
from items.constants import CATEGORIES

from users.models import Customer
from items.models import Item, Combo
from items.models import Item
from django.utils import timezone

# Define days of the week choices
DAYS_OF_WEEK = (
    (0, 'Monday'),
    (1, 'Tuesday'),
    (2, 'Wednesday'),
    (3, 'Thursday'),
    (4, 'Friday'),
    (5, 'Saturday'),
    (6, 'Sunday'),
)

class OrderedItem(models.Model):
    order = models.ForeignKey('Order', on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    rating = models.IntegerField(default=0)

    item = models.ForeignKey(
        Item, 
        on_delete=models.CASCADE, 
        null=True,  # Allows the database field to be NULL
        blank=True  # Allows form submission without a value
    )

    combo = models.ForeignKey(
        Combo, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='ordered_combos' 
    )

    def __str__(self):
        # Safely determine the name of the item/combo.
        if self.item:
            item_name = self.item.name
        elif self.combo:
            item_name = f"COMBO: {self.combo.name}" if self.combo else "DELETED COMBO"
        else:
            item_name = "UNSPECIFIED ITEM"
        return f"{self.quantity} x {item_name} in Order {self.order.id}"


    def calculate_price(self):
        """
        Calculate price based on item or combo
        """
        if self.item:
            self.price = self.item.rate * Decimal(str(self.quantity))
        elif self.combo:
            self.price = self.combo.rate * Decimal(str(self.quantity))
        else:
            self.price = Decimal('0.00')
        self.save()
        return self.price
    
    @property
    def unit_price(self):
        if self.item:
            return self.item.rate
        elif self.combo:
            return self.combo.rate
        return Decimal('0.00')
    
    @property 
    def name(self):
        if self.item:
            return self.item.name
        elif self.combo:
            return f"🎁 {self.combo.name} (Combo)"
        return "Unknown Item"

class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    ordered_items = models.ManyToManyField(OrderedItem, related_name='orders')
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    date_placed = models.DateField(auto_now_add=False, null=True, blank=True)
    time_placed = models.TimeField(auto_now_add=False, null=True, blank=True)
    expected_delivery_time = models.TimeField(auto_now_add=False, null=True, blank=True)
    delivered = models.BooleanField(default=False)
    finalized = models.BooleanField(default=False)
    used_loyalty_points = models.BooleanField(default=False)
    payment_reference = models.CharField(max_length=100, null=True, blank=True)
    hidden_from_customer = models.BooleanField(default=False)

    # Added field to store total price
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return str(self.customer.user.username) + "- " + str(self.date_placed) + " - #" + str(self.id)
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=settings.DEFAULT_DELIVERY_FEE)

    def save(self, *args, **kwargs):
        # CRITICAL FIX: Ensure both operands are Decimal before addition
        subtotal_decimal = Decimal(str(self.subtotal))
        delivery_fee_decimal = Decimal(str(self.delivery_fee))
        
        self.grand_total = subtotal_decimal + delivery_fee_decimal
        
        super(Order, self).save(*args, **kwargs)

    def calculate_totals(self):
        """
        Calculate subtotal, apply discounts, and set grand_total
        """
        ordered_items = self.ordereditem_set.all()
        subtotal = Decimal('0.00')
        
        for item in ordered_items:
            # Make sure each item has its price calculated
            if item.price is None or item.price == Decimal('0.00'):
                item.calculate_price()
            subtotal += item.price
        
        self.subtotal = subtotal
        
        # Apply loyalty discount if used
        discount = Decimal('2500.00') if self.used_loyalty_points else Decimal('0.00')
        
        self.grand_total = max(self.subtotal + self.delivery_fee - discount, Decimal('0.00'))
        self.save()
    
    def refresh_totals(self):
        """
        Force recalculation of all totals
        """
        return self.calculate_totals()

class DeliveryLocation(models.Model):
    """Stores delivery zones (Regions) and their associated fixed fees."""
    name = models.CharField(
        max_length=100, 
        unique=True, 
        help_text="e.g., Campus, College, Off Campus - Tipper Garage (Bus Stop only)"
    )
    fee = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        default=0.00, 
        help_text="Delivery fee in Naira (₦)"
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (₦{self.fee})"

    class Meta:
        verbose_name = "Delivery Region & Fee"
        verbose_name_plural = "Delivery Regions & Fees"

class OperatingHours(models.Model):
    # This field defines which day of the week this schedule applies to
    day = models.IntegerField(choices=DAYS_OF_WEEK, unique=True, null=True, blank=True) 
    
    # You can set specific dates to close (like Christmas or Eid)
    closed_date = models.DateField(null=True, blank=True, help_text="Set a specific date to close (e.g., Public Holiday).")
    
    is_open = models.BooleanField(default=True, help_text="Check to allow ordering on this day/date.")
    opening_time = models.TimeField(null=True, blank=True, help_text="The time ordering opens.")
    closing_time = models.TimeField(null=True, blank=True, help_text="The time ordering closes.")
    
    class Meta:
        verbose_name = "Operating Hour"
        verbose_name_plural = "Operating Hours"
        # Constraint to ensure a single entry for a day or date
        constraints = [
            models.UniqueConstraint(fields=['day'], condition=models.Q(closed_date__isnull=True), name='unique_day_hours'),
        ]
    
    def __str__(self):
        if self.closed_date:
            return f"Holiday Closure: {self.closed_date}"
        
        day_name = self.get_day_display()
        if not self.is_open:
            return f"{day_name} - CLOSED ALL DAY"
            
        open_str = self.opening_time.strftime('%I:%M %p')
        close_str = self.closing_time.strftime('%I:%M %p')
        return f"{day_name}: {open_str} - {close_str}"