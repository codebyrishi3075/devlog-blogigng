from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.mail import send_mail

logger = get_task_logger(__name__)


def _using_console_email_backend():
    return settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend'


def _using_smtp_email_backend():
    return settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'


def send_otp_email_sync(email, otp_code, purpose):
    """
    Send an OTP email immediately in the current process.
    Used by Celery and by local diagnostics/fallbacks.
    """
    subject_map = {
        'REGISTER': 'DevLog - Verify your email',
        'FORGOT_PASSWORD': 'DevLog - Password reset OTP',
    }
    message = f"""
    Your OTP for {purpose.replace('_', ' ').title()} is:

    {otp_code}

    This OTP is valid for 10 minutes.
    Do not share it with anyone.
    """
    if _using_smtp_email_backend():
        missing_settings = [
            name for name in ('EMAIL_HOST', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD')
            if not getattr(settings, name, None)
        ]
        if missing_settings:
            raise RuntimeError(
                "Email OTP is not configured. Missing settings: "
                + ", ".join(missing_settings)
            )

    return send_mail(
        subject=subject_map.get(purpose, 'DevLog OTP'),
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name='accounts.tasks.send_otp_email_task'
)
def send_otp_email_task(self, email, otp_code, purpose):
    """
    Celery task to send OTP email in background.
    Retries up to 3 times if it fails.
    """
    try:
        send_otp_email_sync(email, otp_code, purpose)
        logger.info(f"OTP email sent to {email} for purpose {purpose}")

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            logger.exception(
                "OTP email failed permanently after 3 retries. "
                "email=%s purpose=%s otp=%s error=%s",
                email,
                purpose,
                otp_code,
                exc,
            )
            raise

        logger.warning(
            "Failed to send OTP email to %s. retry=%s/%s error=%s",
            email,
            self.request.retries + 1,
            self.max_retries,
            exc,
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name='accounts.tasks.send_otp_sms_task'
)
def send_otp_sms_task(self, phone_number, otp_code, purpose):
    """
    Celery task to send OTP SMS via Twilio in background.
    Retries up to 3 times if it fails.
    """
    missing_settings = [
        name for name in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER')
        if not getattr(settings, name, None)
    ]
    if missing_settings:
        raise RuntimeError(
            "SMS OTP is not configured. Missing settings: "
            + ", ".join(missing_settings)
        )

    try:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        purpose_text = purpose.replace('_', ' ').title()
        client.messages.create(
            body=f"Your DevLog OTP for {purpose_text} is: {otp_code}. Valid for 10 minutes.",
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        logger.info(f"OTP SMS sent to {phone_number} for purpose {purpose}")

    except Exception as exc:
        logger.error(f"Failed to send OTP SMS to {phone_number}. Error: {exc}")
        raise self.retry(exc=exc)
