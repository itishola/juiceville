from django.db import models
from decimal import Decimal
from datetime import timedelta, datetime
import random
import smtplib
from email.message import EmailMessage
from django.conf import settings

def calculate_item_ratings(ordered_items):
    for oitem in ordered_items:
        total_rating = oitem.item.rating * oitem.item.times_rated
        oitem.item.times_rated += 1
        oitem.item.rating = (total_rating + oitem.rating) / oitem.item.times_rated
        oitem.item.save()

def calculate_grand_total_and_update_stocks(order, ordered_items):
    grand_total = Decimal('0.00')
    
    for oitem in ordered_items:
        # 1. Update Grand Total (This is always safe)
        grand_total += oitem.price
        
        # 2. Deduct Stock (MUST check which type of object is being ordered)
        
        # A. Handle Individual Items
        if oitem.item:
            # Check if oitem.item exists before accessing its stock
            item = oitem.item
            if item.stock >= oitem.quantity:
                item.stock -= oitem.quantity
                item.save()
            else:
                # Optional: Handle critical low stock error
                print(f"ERROR: Insufficient stock for individual item {item.name}")

        # B. Handle Combos (Deduct stock from the Combo's components)
        elif oitem.combo:
            combo = oitem.combo
            quantity = oitem.quantity
            
            # Assuming Combo model has item1, item2, item3, etc. fields
            component_fields = [combo.item1, combo.item2, combo.item3, combo.item4, combo.item5]

            # Iterate through all non-null component items of the combo
            for component_item in component_fields:
                if component_item:
                    deduct_qty = quantity
                    
                    if component_item.stock >= deduct_qty:
                        component_item.stock -= deduct_qty
                        component_item.save()
                    else:
                        # Optional: Handle critical low stock error
                        print(f"ERROR: Insufficient stock for component {component_item.name} in combo {combo.name}")
        
        # C. Handle Corrupt OrderedItem (Neither item nor combo is set)
        else:
            print(f"WARNING: OrderedItem {oitem.id} has no item or combo association and was skipped for stock deduction.")
            continue


    order.grand_total = grand_total
    order.save()

def calculate_expected_delivery_time(order):
    order.expected_delivery_time = datetime.now() + timedelta(minutes=45)
    order.save()

def mail_customers(customers, offer_text):
    try:
        # 1. Use SMTP_SSL for Port 465
        with smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT) as smtp:
            
            # 2. Introduce client
            smtp.ehlo() 
            
            # 3. Login using the App Password
            smtp.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)

            # ... 4. Send Emails ...
            for customer in customers:
                if customer.user.email:
                    msg = EmailMessage()
                    msg['Subject'] = 'Special Offer from Juiceville!'
                    msg['From'] = settings.EMAIL_HOST_USER
                    msg['To'] = customer.user.email
                    msg.set_content(offer_text)
                    
                    smtp.send_message(msg)

    except Exception as e:
        print(f"An error occurred while sending email: {e}")
        raise