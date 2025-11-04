# orders/notifications.py 

import requests
from django.conf import settings
from django.urls import reverse
from datetime import datetime
from decimal import Decimal

# HARD-CODED WORKING VALUES FOR DEBUGGING
DEBUG_BOT_TOKEN = '7379387313:AAGp9hvaLtsYotoNZpNNddUrjatCWHiDJho'

# 🛑 CRITICAL: REPLACE THE PLACEHOLDER BELOW WITH YOUR ACTUAL NEGATIVE CHAT ID
DEBUG_CHAT_ID = '-1003010450709' # Example: Use your actual negative number

def send_telegram_alert(order):
    
    # 🚨 DEBUG: USE HARD-CODED VALUES TO BYPASS SETTINGS.PY
    bot_token = DEBUG_BOT_TOKEN
    chat_id = DEBUG_CHAT_ID
    
    # Ensure BASE_URL is set correctly in settings.py
    base_url = getattr(settings, 'BASE_URL', None)
    if not base_url:
        print("ERROR: BASE_URL is not set in settings.py.")
        return
        
    # Build the URL for the staff to view the order details
    try:
        # NOTE: The URL name in urls.py is 'staff_order_details'
        order_detail_url_path = reverse('orders:staff_order_details', args=[order.id]) 
        order_link = f"{base_url}{order_detail_url_path}"
    except Exception as e:
        print(f"URL reverse failed: {e}")
        # Fallback to Admin link if the staff URL is missing
        order_link = f"{base_url}/admin/orders/order/{order.id}/change/" 


    # 🛑 FIX 1: Construct the message using HTML tags 🛑
    message = (
        f"<b>🚨 NEW ORDER!</b> (Paid)\n"
        f"<b>🆔 Order ID:</b> <code>{order.id}</code>\n"
        f"<b>💰 Total:</b> ₦{order.grand_total:,.2f}\n" # No bold around the number for safety
        f"<b>👤 Customer:</b> {order.customer.name}\n"
        f"<b>🕒 Time:</b> {datetime.now().strftime('%H:%M %p')}\n\n"
        # 🛑 FIX 2: Correct HTML link construction
        f'<a href="{order_link}">VIEW DETAILS</a>' 
    )

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML', # 🛑 CRITICAL FIX 3: Switched from Markdown to HTML
        'disable_web_page_preview': True
    }

    try:
        response = requests.post(api_url, data=payload, timeout=5)
        response.raise_for_status() 
        
        print(f"Telegram API Response Status: {response.status_code}")
        print(f"Telegram API Response Text: {response.text}")
        
    except requests.exceptions.RequestException as e:
        print(f"CRITICAL REQUESTS ERROR: {e}")