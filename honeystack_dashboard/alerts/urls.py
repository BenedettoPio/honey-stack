from django.urls import re_path

from honeystack_dashboard.alerts import views

urlpatterns = [
    re_path(r'^$', views.IndexView.as_view(), name='index'),
]
