from django.db import models
from PIL import Image
from decimal import Decimal
from django_resized import ResizedImageField

from items.constants import CATEGORIES

class Item(models.Model):
    name = models.CharField(max_length=50)
    category = models.CharField(max_length=50, choices=CATEGORIES)
    description = models.TextField(max_length=500)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    is_non_veg = models.BooleanField(default=False)    
    stock = models.IntegerField(default=10)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=5)
    image = models.ImageField(verbose_name="Feature Image", upload_to="item_pics", default="media/default_item.png")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    #non_availablity_time = models.DateTimeField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        img = Image.open(self.image.path)

        if img.height>300 or img.width > 300:
            output_size = (300, 300)
            img.thumbnail(output_size)
            img.save(self.image.path)

    def __str__(self):
        # This tells Django Admin to display the Item's name
        return self.name
    
    image = ResizedImageField(
        size=[800, 800],
        quality=85,
        upload_to='item_images/',
        force_format='WEBP',
        blank=True,
        null=True
    )
    thumbnail = ResizedImageField(
        size=[150, 150],
        quality=80,
        upload_to='item_thumbnails/',
        force_format='WEBP',
        blank=True,
        null=True
    )
            
class Combo(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    image = models.ImageField(upload_to='combos_images/', blank=True, null=True)

    # 🛑 ADJUSTMENT: Set required=False for now, as it's set in save()
    rate = models.DecimalField(max_digits=10, decimal_places=2) 
    
    # Optional Item Foreign Keys (as per previous fix)
    item1 = models.ForeignKey('Item', on_delete=models.SET_NULL, related_name='combo_item1', blank=True, null=True)
    item2 = models.ForeignKey('Item', on_delete=models.SET_NULL, related_name='combo_item2', blank=True, null=True)
    item3 = models.ForeignKey('Item', on_delete=models.SET_NULL, related_name='combo_item3', blank=True, null=True)
    item4 = models.ForeignKey('Item', on_delete=models.SET_NULL, related_name='combo_item4', blank=True, null=True)
    item5 = models.ForeignKey('Item', on_delete=models.SET_NULL, related_name='combo_item5', blank=True, null=True)
    
    stock = models.IntegerField(default=0)
    
    def calculate_rate(self):
        """Calculates the rate by summing items and applying a 5% discount."""
        total_price = Decimal('0.00')
        
        # Iterate through all item fields
        item_fields = [self.item1, self.item2, self.item3, self.item4, self.item5]
        
        for item in item_fields:
            if item:
                # Assuming your Item model has a 'price' attribute
                total_price += item.price 
                
        # 🛑 IMPLEMENT 5% DISCOUNT (1 - 0.05 = 0.95)
        discount_factor = Decimal('0.95')
        
        # Return 5% discounted price, ensuring it's not negative
        return max(total_price * discount_factor, Decimal('0.00'))


    def save(self, *args, **kwargs):
        # 🛑 ENSURE RATE IS CALCULATED BEFORE SAVING
        self.rate = self.calculate_rate()

        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.name
            
    @property
    def effective_stock(self):
        """
        Calculates the maximum number of times this combo can be sold,
        limited by the component item with the lowest stock.
        """
        item_fields = [self.item1, self.item2, self.item3, self.item4, self.item5]
        
        # Start with a very high number to find the minimum
        min_stock = float('inf')
        
        for item in item_fields:
            if item:
                # Assuming item.stock is an integer field
                if item.stock < min_stock:
                    min_stock = item.stock
        
        # If no items are selected in the combo, it's considered unlimited (or 0, safer to return 0)
        return int(min_stock) if min_stock != float('inf') else 0

    def __str__(self):
        return self.name
# Create your models here.
