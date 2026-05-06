from datetime import timedelta
import logging

from django.conf import settings
from django.utils import timezone

from .models import OTP
from .rate_limiter import otp_rate_limiter
from .tasks import send_otp_email_sync, send_otp_email_task, send_otp_sms_task

logger = logging.getLogger(__name__)


def create_and_send_otp(purpose, channel, email=None, phone_number=None, user=None):
    """
    Central OTP dispatch function.
    - Rate limit check
    - Invalidate old OTPs
    - Create new OTP record
    - Fire Celery task (non-blocking)
    """
    identifier = email or phone_number
    if not identifier:
        raise ValueError("Either email or phone_number is required to send an OTP.")

    # Rate limit check
    allowed, message, _ = otp_rate_limiter.can_request_otp(identifier, purpose)
    if not allowed:
        raise PermissionError(message)

    # Invalidate old unverified OTPs
    old_otps = OTP.objects.filter(purpose=purpose, is_verified=False)
    if email:
        old_otps = old_otps.filter(email=email)
    if phone_number:
        old_otps = old_otps.filter(phone_number=phone_number)
    old_otps.delete()

    # Create fresh OTP
    otp_code = OTP.generate_otp()
    otp = OTP.objects.create(
        user=user,
        email=email,
        phone_number=phone_number,
        otp_code=otp_code,
        purpose=purpose,
        channel=channel,
        expires_at=timezone.now() + timedelta(minutes=10),
    )

    # Fire Celery task. In local development this runs eagerly by default; if
    # broker enqueue fails, email still has a synchronous fallback.
    if channel == 'EMAIL' and email:
        try:
            async_result = send_otp_email_task.delay(email, otp_code, purpose)
            logger.info("Queued OTP email task id=%s email=%s purpose=%s", async_result.id, email, purpose)
        except Exception as exc:
            logger.exception(
                "Could not enqueue OTP email task; sending synchronously. "
                "email=%s purpose=%s error=%s",
                email,
                purpose,
                exc,
            )
            try:
                send_otp_email_sync(email, otp_code, purpose)
            except Exception:
                otp.delete()
                raise

    elif channel == 'SMS' and phone_number:
        try:
            async_result = send_otp_sms_task.delay(phone_number, otp_code, purpose)
            logger.info("Queued OTP SMS task id=%s phone=%s purpose=%s", async_result.id, phone_number, purpose)
        except Exception as exc:
            logger.warning(
                "Could not send or enqueue OTP SMS. phone=%s purpose=%s error=%s",
                phone_number,
                purpose,
                exc,
            )
            otp.delete()
            raise

    else:
        otp.delete()
        raise ValueError(f"Unsupported OTP channel or missing destination: {channel}")

    # Increment rate limit counter
    otp_rate_limiter.increment_request_count(identifier, purpose)

    return otp


def verify_otp(purpose, otp_code, email=None, phone_number=None):
    """
    Returns (success: bool, message: str, otp_instance or None)
    Tracks failed attempts via Redis.
    """
    identifier = email or phone_number

    # Lockout check
    if otp_rate_limiter.is_locked_out(identifier, purpose):
        return False, "Too many failed attempts. Try again after 30 minutes.", None

    try:
        filters = {
            'purpose': purpose,
            'otp_code': otp_code,
            'is_verified': False
        }
        if email:
            filters['email'] = email
        if phone_number:
            filters['phone_number'] = phone_number

        otp = OTP.objects.get(**filters)

    except OTP.DoesNotExist:
        # Record failed attempt
        locked = otp_rate_limiter.record_failed_verification(identifier, purpose)
        if locked:
            return False, "Too many failed attempts. Account locked for 30 minutes.", None
        return False, "Invalid OTP.", None

    if otp.is_expired():
        return False, "OTP has expired. Please request a new one.", None

    # Success - mark verified and clear fail counters
    otp.is_verified = True
    otp.save()
    otp_rate_limiter.clear_failed_attempts(identifier, purpose)

    return True, "OTP verified successfully.", otp
