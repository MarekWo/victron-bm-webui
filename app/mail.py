"""SMTP email sending for victron-bm-webui."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

log = logging.getLogger(__name__)


def send_email(
    smtp_config: dict[str, Any],
    subject: str,
    body: str,
) -> bool:
    """Send an email notification using SMTP.

    Args:
        smtp_config: SMTP configuration dictionary with keys:
            server, port, use_tls, username, password,
            sender_name, sender_email, recipients.
        subject: Email subject line.
        body: Email body (plain text).

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    if not smtp_config.get("enabled", False):
        log.debug("SMTP disabled, skipping email: %s", subject)
        return False

    recipients = smtp_config.get("recipients", [])
    if not recipients:
        log.warning("No email recipients configured")
        return False

    server_host = smtp_config.get("server", "")
    if not server_host:
        log.warning("SMTP server not configured")
        return False

    sender_name = smtp_config.get("sender_name", "Victron BM Monitor")
    sender_email = smtp_config.get("sender_email", "")
    port = smtp_config.get("port", 587)
    use_tls = smtp_config.get("use_tls", True)
    username = smtp_config.get("username", "")
    password = smtp_config.get("password", "")

    msg = MIMEMultipart()
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        if use_tls:
            server = smtplib.SMTP(server_host, port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP(server_host, port, timeout=30)
            server.ehlo()

        if username and password:
            server.login(username, password)

        server.sendmail(sender_email, recipients, msg.as_string())
        server.quit()

        log.info("Email sent: %s -> %s", subject, ", ".join(recipients))
        return True

    except Exception:
        log.exception("Failed to send email: %s", subject)
        return False
