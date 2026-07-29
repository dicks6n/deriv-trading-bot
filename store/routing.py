# store/routing.py
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/trading/', consumers.TradingConsumer.as_asgi()),
]