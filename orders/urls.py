# orders/urls.py

from django.urls import path
from django.urls import reverse
from django.views.generic import TemplateView
from .views import *

app_name = 'orders'

urlpatterns = [
    path('', index, name="index"),
    path('test-menu/', test_menu, name="test_menu"),
    path('menu/', test_menu, name="menu"), 
    path('create-order/', create_order, name="create_order"),
    path('<int:pk>/add-items/', add_items, name="add_items"),
    path('<int:pk>/finalize/', finalize_order, name="finalize_order"),
    path('<int:pk>/summary/', order_summary, name="order_summary"),
        
    path('<int:pk>/delete/', delete_order, name="delete_order"),
    path('past-transactions/', past_transactions, name="past_transactions"),
    path('generate-sales/', generate_sales, name="generate_sales"),
    path('notify-offers/', notify_offers, name="notify_offers"),
    path('<int:pk>/apply-loyalty-points/', apply_loyalty_points, name="apply_loyalty_points"),
    path('<int:pk>/initiate-payment/', initiate_payment, name="initiate_payment"),
    path('close-order/<int:pk>/', close_order, name='close_order'),
    path('update-stock/', update_stock, name='update_stock'),
    path('my-orders/', customer_past_transactions, name='customer_past_transactions'),
    path('my-orders/<int:order_id>/', transaction_detail, name='transaction_detail'),
    path('generate_sales/', generate_sales, name='generate_sales'),
    path('staff-order/<int:order_id>/', staff_order_details, name='staff_order_details'),

    path('checkout/', checkout, name='checkout'),
    path('payment/<int:order_id>/', payment, name='payment'),
    path('day-orders/', day_orders, name='day_orders'),
    path('monthly-report/', monthly_report, name='monthly_report'),
    path('hide-order/<int:pk>/', hide_order, name='hide_order'),
    path('cleanup-orders/', cleanup_orders, name='cleanup_orders'),
    
    path('mg/customers/', customer_management, name='customer_management'),
    path('mg/customers/export/', export_customers_csv, name='export_customers_csv'),
    path('mg/customers/analytics/', customer_analytics, name='customer_analytics'),
    path('all-transactions/', all_transactions, name='all_transactions'),
    path('daily-report/', daily_report, name='daily_report'),
    path('mg-dashboard/', mg_dashboard, name='mg_dashboard'),
    path('mg/customers/export-analytics/', export_analytics_csv, name='export_analytics_csv'),
    path('offline/', TemplateView.as_view(template_name='orders/offline.html'), name='offline'),
]