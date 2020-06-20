# -*- coding:utf-8 -*-
from django.shortcuts import render, redirect, HttpResponse
from saas.forms.account import RegisterModelForm, SendSmsForm, LoginSmsForm, LoginForm
from django.http import JsonResponse
from saas import models
from utils.image_code import check_code
from io import BytesIO
from django.db.models import Q
import uuid
import datetime


# 关于用户账户的相关功能，注册、登录、注销等。

def register(request):
    if request.method == "POST":  # 如果来的是POST请求...
        form = RegisterModelForm(data=request.POST)  # 将request携带的数据送给ModelForm进行校验
        if form.is_valid():  # 如果request携带的数据通过了ModelForm的表单验证...
            user_object = form.save()  # form简洁方便 将数据写入数据库
            # data = form.cleaned_data.pop('code').pop('confirm_password')
            # models.UserInfo.objects.create(**data)

            # 创建交易记录
            policy_object = models.PricePolicy.objects.filter(category=1, title="个人免费版").first()

            models.Transaction.objects.create(
                status=2,
                order=str(uuid.uuid4()),
                user=user_object,
                price_policy=policy_object,
                count=0,
                price=0,
                start_datetime=datetime.datetime.now()
            )

            return JsonResponse({"status": True, "data": "/login/"})
        return JsonResponse({"status": False, "error": form.errors})
    form = RegisterModelForm()
    return render(request, "register.html", {'form': form})


def send_sms(request):
    """ 发送短信 """

    form = SendSmsForm(request, data=request.GET)
    if form.is_valid():
        return JsonResponse({'status': True})
    return JsonResponse({"status": False, "error": form.errors})


def login_sms(request):
    if request.method == "POST":
        form = LoginSmsForm(request.POST)  # 用来的数据实例化Form，准备校验
        if form.is_valid():  # 如果数据通过来Form的校验...
            # 用户信息存入session中
            user_object = form.cleaned_data.get("mobile_phone")
            request.session['user_id'] = user_object.id
            request.session.set_expiry(60 * 60 * 24 * 14)
            return JsonResponse({"status": True, "data": "/index/"})

        return JsonResponse({"status": False, "error": form.errors})
    form = LoginSmsForm()
    return render(request, "login_sms.html", {"form": form})


def login(request):
    """ 手机号或邮箱登录"""

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)  # 用来的数据实例化Form，准备校验
        if form.is_valid():  # 如果数据通过来Form的校验...

            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            # user_object = models.UserInfo.objects.filter(username=username, password=password).first()
            #  (手机=username and pwd=pwd) or (邮箱=username and pwd=pwd)
            user_object = models.UserInfo.objects.filter(Q(email=username) | Q(mobile_phone=username)).filter(
                password=password).first()
            if user_object:
                # 登录成功
                request.session['user_id'] = user_object.id
                request.session.set_expiry(60 * 60 * 24 * 14)
                return redirect('index')
            form.add_error("username", "用户名或密码错误错误")
        return render(request, "login.html", {"form": form})
    form = LoginForm(request)
    return render(request, "login.html", {"form": form})


def image_code(request):
    image_object, code = check_code()

    request.session['image_code'] = code
    request.session.set_expiry(60)  # 主动修改session的过期时间

    stream = BytesIO()
    image_object.save(stream, 'png')
    return HttpResponse(stream.getvalue())


def logout(request):
    request.session.flush()
    return redirect('login')
