from django.urls import path
from .models import User

from .views import SignUp
from .views import Login

urlpatterns = [
    path('signup', SignUp, name='signup'),
    path('login', Login, name='login')
]