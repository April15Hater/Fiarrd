"""
modules/mailer.py — Email sending via LAN SMTP relay.

Relay at 192.168.1.24:25 accepts unauthenticated connections from the LAN;
no TLS or SASL needed inside the network. Override with env vars if needed.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SENDER_NAME, SMTP_FROM, SMTP_HOST, SMTP_PORT


def send_email(to_addr: str, subject: str, body: str) -> None:
    """Send a plain-text email via the LAN SMTP relay.

    Raises smtplib.SMTPException (or socket errors) on failure — callers
    should catch and return a user-friendly error.
    """
    msg = MIMEMultipart()
    msg["From"] = f"{SENDER_NAME} <{SMTP_FROM}>"
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.sendmail(SMTP_FROM, [to_addr], msg.as_string())
