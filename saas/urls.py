from django.conf.urls import url, include
from saas.views import account

urlpatterns = [

    url(r'^$', home.index),  # register

    url(r'^register/$', account.register, name='register'),  # register
    url(r'^login/$', account.login, name='login'),
]
