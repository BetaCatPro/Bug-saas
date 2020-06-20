from django import forms
from web import models
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.conf import settings
from utils.tencent.sms import send_sms_single
import random
from django_redis import get_redis_connection
from utils import encrypt
from web.forms.bootstrap import BootStrapForm


class RegisterModelForm(BootStrapForm, forms.ModelForm):
    mobile_phone = forms.CharField(
        label="手机号",
        validators=[RegexValidator(r'^(1[3|4|5|6|7|8|9])\d{9}$', "手机号格式错误"), ]
    )
    password = forms.CharField(
        label="密码",
        widget=forms.PasswordInput(),
        min_length=6,
        max_length=16,
        error_messages={
            "min_length": "密码长度不能小于8位",
            "max_length": "密码长度不能大于16位"
        }
    )
    confirm_password = forms.CharField(
        label="重复密码",
        min_length=6,
        max_length=16,
        error_messages={
            "min_length": "重复密码长度不能小于8位",
            "max_length": "重复密码长度不能大于16位"
        },
        widget=forms.PasswordInput()
    )
    code = forms.CharField(label="验证码", widget=forms.TextInput())

    class Meta:
        model = models.UserInfo
        fields = ['username', 'email', 'password', 'confirm_password', 'mobile_phone', 'code']

    # def __init__(self, *args, **kwargs):  # 重写父类__init__()方法，给字段加属性，达到给每个input标签加样式的目的。
    #     super().__init__(*args, **kwargs)
    #     for name, field in self.fields.items():
    #         field.widget.attrs['class'] = 'form-control'
    #         field.widget.attrs['placeholder'] = '请输入%s' % field.label

    def clean_username(self):
        username = self.cleaned_data.get("username")
        exists = models.UserInfo.objects.filter(username=username).exists()
        if exists:
            raise ValidationError("用户名已存在")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")
        exists = models.UserInfo.objects.filter(email=email).exists()
        if exists:
            raise ValidationError("邮箱已存在")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        password = encrypt.md5(password)
        return password

    def clean_confirm_password(self):
        password = self.cleaned_data.get("password")
        confirm_password = self.cleaned_data.get("confirm_password")
        confirm_password = encrypt.md5(confirm_password)
        if password != confirm_password:  # 如果两次密码不一样，则...
            raise ValidationError("两次密码不一致")
        return confirm_password

    def clean_mobile_phone(self):
        mobile_phone = self.cleaned_data.get("mobile_phone")
        exists = models.UserInfo.objects.filter(mobile_phone=mobile_phone).exists()
        if exists:
            # self.add_error("mobile_phone", "手机号已存在") # 正常走return，后续不会出错
            raise ValidationError("手机号已存在")  # 不会走return，后续若要用到，可能会报错
        return mobile_phone

    def clean_code(self):
        code = self.cleaned_data.get("code")
        mobile_phone = self.cleaned_data.get("mobile_phone")
        if not mobile_phone:  # 如果从干净数据中拿不到mobile_phone（手机号校验没过）...
            return code
        # 去redis中读取验证码
        conn = get_redis_connection()
        redis_code = conn.get(mobile_phone)
        if not redis_code:  # 如果库中验证码过期，则...
            raise ValidationError("短信验证码失效或未发送，请重新发送")
        redis_code = redis_code.decode("utf-8")
        if code.strip() != redis_code.strip():
            raise ValidationError("短信验证码错误，请重新输入")
        return code


class SendSmsForm(forms.Form):
    mobile_phone = forms.CharField(
        label="手机号",
        validators=[RegexValidator(r'^(1[3|4|5|6|7|8|9])\d{9}$', "手机号格式错误"), ]
    )

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

    def clean_mobile_phone(self):
        """ 手机号校验的钩子"""
        mobile_phone = self.cleaned_data.get("mobile_phone")
        tpl = self.request.GET.get('tpl')

        # 校验数据库中是否已有手机号
        exists = models.UserInfo.objects.filter(mobile_phone=mobile_phone).exists()
        if tpl == 'register' and exists:
            raise ValidationError('手机号已存在')
        if tpl == "login" and not exists:
            raise ValidationError("手机号不存在")

        # 判断短信模板是否有问题
        template_id = settings.TENCENT_SMS_TEMPLATE.get(tpl)
        if not template_id:
            raise ValidationError('短信模板错误')

        # 发送短信
        code = random.randrange(100000, 999999)
        sms = send_sms_single(mobile_phone, template_id, [code, ])
        if sms["result"] != 0:
            raise ValidationError("短信发送失败,{}".format(sms["errmsg"]))

        # 验证码写入redis中
        conn = get_redis_connection()
        conn.set(mobile_phone, code, ex=300)

        return mobile_phone


class LoginSmsForm(BootStrapForm, forms.Form):
    mobile_phone = forms.CharField(
        label="手机号",
        validators=[RegexValidator(r'^(1[3|4|5|6|7|8|9])\d{9}$', "手机号格式错误"), ]
    )
    code = forms.CharField(label="验证码", widget=forms.TextInput())

    def __init__(self, *args, **kwargs):  # 重写父类__init__()方法，给字段加属性，达到给每个input标签加样式的目的。
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
            field.widget.attrs['placeholder'] = '请输入%s' % field.label

    def clean_mobile_phone(self):
        mobile_phone = self.cleaned_data.get("mobile_phone")
        # exists = models.UserInfo.objects.filter(mobile_phone=mobile_phone).exists()
        user_object = models.UserInfo.objects.filter(mobile_phone=mobile_phone).first()
        if not user_object:  # 如果数据库中没有查到该手机号用户...
            self.add_error("mobile_phone", "手机号不存在")
        return user_object

    def clean_code(self):
        code = self.cleaned_data.get("code")
        user_object = self.cleaned_data.get("mobile_phone")
        if not user_object:  # 如果干净数据中找不到mobile_phone（手机号校验没过）...
            return code
        mobile_phone = user_object.mobile_phone
        conn = get_redis_connection()
        redis_code = conn.get(mobile_phone)
        if not redis_code:  # 如果库中验证码过期，则...
            raise ValidationError("短信验证码失效或未发送，请重新发送")
        redis_code = redis_code.decode("utf-8")
        if code.strip() != redis_code.strip():  # 如果验证码一样...
            raise ValidationError("短信验证码错误，请重新输入")
        return code


class LoginForm(BootStrapForm, forms.Form):
    username = forms.CharField(label='邮箱或手机号')
    password = forms.CharField(label='密码', widget=forms.PasswordInput(render_value=True))
    code = forms.CharField(label='图片验证码')

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

    def clean_password(self):
        pwd = self.cleaned_data.get("password")
        # 加密 & 返回
        return encrypt.md5(pwd)

    def clean_code(self):
        """ 钩子，校验图片验证码是否正确"""

        # 用户输入的验证码
        code = self.cleaned_data.get("code")

        # 拿session中的保存的验证码
        session_code = self.request.session.get("image_code")
        if not session_code:  # 如果在session中找不到验证码（过期）...
            raise ValidationError("验证码已过期，请重新获取")

        if code.strip().upper() != session_code.strip().upper():  # 如果用户输入的验证码跟session中保持的验证码不一样...
            raise ValidationError("验证码错误，请重新输入")
        return code
