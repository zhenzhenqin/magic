from collections import deque
from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
import ssl
from threading import Lock
from typing import Protocol


class EmailProvider(Protocol):
    def send(self, email: str, purpose: str, code: str) -> None: ...


@dataclass(frozen=True, repr=False)
class CapturedCode:
    email: str
    purpose: str
    code: str


class CaptureEmailProvider:
    def __init__(self):
        self.messages = deque(maxlen=128)
        self.lock = Lock()

    def send(self, email, purpose, code):
        with self.lock:
            self.messages.append(CapturedCode(email, purpose, code))


class SmtpEmailProvider:
    def __init__(self, settings):
        self.settings = settings

    def send(self, email, purpose, code):
        settings = self.settings
        message = EmailMessage()
        message["From"], message["To"] = settings.smtp_sender, email
        message["Subject"] = "FoodDiary 邮箱验证码"
        action = {"login": "登录", "register": "注册", "reset": "重设密码",
                  "bind": "绑定邮箱", "change": "更换邮箱"}[purpose]
        message.set_content(f"你正在{action} FoodDiary。验证码为 {code}，5 分钟内有效、仅可使用一次。")
        tls = ssl.create_default_context()
        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(settings.smtp_host, 465, timeout=8, context=tls)
        else:
            server = smtplib.SMTP(settings.smtp_host, 587, timeout=8)
        with server:
            if settings.smtp_port == 587:
                server.ehlo()
                server.starttls(context=tls)
                server.ehlo()
            server.login(settings.smtp_username, settings.smtp_authorization_code.get_secret_value())
            server.send_message(message)
