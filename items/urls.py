# from django.contrib.auth import views as auth_views

from django.contrib import admin
from django.urls import path, include
from orders.views import index

from django.conf import settings
from django.conf.urls.static import static
from items.views import *

app_name = 'items'

urlpatterns = [
    
    path('create_item', create_item, name='create_item'),
    
    path('<int:pk>/update_item', update_item, name='update_item'),
    
    path('create_combo', create_combo, name='create_combo'),
    
    path('<int:pk>/update_combo', update_combo, name='update_combo'),

    path('menu/', menu_view, name='menu'), 

]