from django.urls import path
from sage_api.views import ask_question, health_check

urlpatterns = [
    path('ask', ask_question, name='ask'),
    path('health', health_check, name='health'),
]
