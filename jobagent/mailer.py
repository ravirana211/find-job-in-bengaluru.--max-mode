"""Sends email through Gmail SMTP using an app password."""

import smtplib
from email.message import EmailMessage


def send(gmail_address: str, app_password: str, to: str, subject: str, html: str, text: str) -> None:
    msg = EmailMessage()
    msg["From"] = gmail_address
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as smtp:
        smtp.login(gmail_address, app_password)
        smtp.send_message(msg)
