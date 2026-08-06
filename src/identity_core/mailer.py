"""Injectable email sender. No Flask / EmailTemplate dependency."""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol
from urllib import error, request

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    def send(self, to: str, subject: str, html: str) -> None: ...


@dataclass
class MemoryMailer:
    """Test / dry-run mailer that stores messages in memory."""

    outbox: list[dict] = field(default_factory=list)

    def send(self, to: str, subject: str, html: str) -> None:
        self.outbox.append({"to": to, "subject": subject, "html": html})
        logger.info("MemoryMailer: to=%s subject=%s", to, subject)


@dataclass
class LoggingMailer:
    """Fallback that only logs (useful when no SMTP configured)."""

    def send(self, to: str, subject: str, html: str) -> None:
        logger.warning("LoggingMailer (no real delivery): to=%s subject=%s", to, subject)


@dataclass
class SmtpMailer:
    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    sender: str = "noreply@example.com"

    def send(self, to: str, subject: str, html: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.sendmail(self.sender, [to], msg.as_string())


@dataclass
class SendGridMailer:
    api_key: str
    sender: str = "noreply@example.com"

    def send(self, to: str, subject: str, html: str) -> None:
        import json

        payload = json.dumps(
            {
                "personalizations": [{"to": [{"email": to}]}],
                "from": {"email": self.sender},
                "subject": subject,
                "content": [{"type": "text/html", "value": html}],
            }
        ).encode("utf-8")
        req = request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                if resp.status not in (200, 202):
                    raise RuntimeError(f"SendGrid status {resp.status}")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"SendGrid error {exc.code}: {body}") from exc


def mailer_from_env() -> EmailSender:
    sg_key = os.environ.get("SENDGRID_API_KEY", "").strip()
    if sg_key:
        return SendGridMailer(
            api_key=sg_key,
            sender=os.environ.get("SENDGRID_FROM_EMAIL")
            or os.environ.get("MAIL_DEFAULT_SENDER")
            or "noreply@example.com",
        )
    host = os.environ.get("MAIL_SERVER", "").strip()
    if host:
        return SmtpMailer(
            host=host,
            port=int(os.environ.get("MAIL_PORT", "587")),
            username=os.environ.get("MAIL_USERNAME") or None,
            password=os.environ.get("MAIL_PASSWORD") or None,
            use_tls=os.environ.get("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes"),
            sender=os.environ.get("MAIL_DEFAULT_SENDER") or "noreply@example.com",
        )
    return LoggingMailer()
