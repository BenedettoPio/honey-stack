from django.urls import re_path

from honeystack_dashboard.honeytokens import views

urlpatterns = [
    re_path(r'^$', views.IndexView.as_view(), name='index'),
    re_path(r'^create/$', views.CreateView.as_view(), name='create'),
    re_path(r'^(?P<nome>[^/]+)/files/(?P<file>clouds\.yaml|openrc)$',
            views.DownloadView.as_view(), name='download'),
]
