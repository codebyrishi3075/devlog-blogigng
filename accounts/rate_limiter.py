from django.core.cache import cache


class OTPRateLimiter:
    """
    Prevents OTP abuse using Redis.

    Rules:
      - Max 3 OTP requests per identifier per 10 minutes
      - Max 5 failed OTP verify attempts per identifier per 30 minutes
      - Lockout for 30 minutes after 5 failed attempts
    """

    OTP_REQUEST_LIMIT = 3
    OTP_REQUEST_WINDOW = 10 * 60        # 10 minutes in seconds

    VERIFY_FAIL_LIMIT = 5
    VERIFY_FAIL_WINDOW = 30 * 60        # 30 minutes in seconds
    LOCKOUT_DURATION = 30 * 60          # 30 minutes lockout

    @staticmethod
    def _request_key(identifier, purpose):
        return f"otp_request:{purpose}:{identifier}"

    @staticmethod
    def _fail_key(identifier, purpose):
        return f"otp_fail:{purpose}:{identifier}"

    @staticmethod
    def _lockout_key(identifier, purpose):
        return f"otp_lockout:{purpose}:{identifier}"

    def is_locked_out(self, identifier, purpose):
        key = self._lockout_key(identifier, purpose)
        return cache.get(key) is not None

    def can_request_otp(self, identifier, purpose):
        """Returns (allowed: bool, message: str, remaining: int)"""

        if self.is_locked_out(identifier, purpose):
            return False, "Too many failed attempts. Try again after 30 minutes.", 0

        key = self._request_key(identifier, purpose)
        count = cache.get(key, 0)

        if count >= self.OTP_REQUEST_LIMIT:
            return False, f"Maximum {self.OTP_REQUEST_LIMIT} OTP requests allowed per 10 minutes.", 0

        remaining = self.OTP_REQUEST_LIMIT - count - 1
        return True, "OK", remaining

    def increment_request_count(self, identifier, purpose):
        key = self._request_key(identifier, purpose)
        count = cache.get(key, 0)
        cache.set(key, count + 1, timeout=self.OTP_REQUEST_WINDOW)

    def record_failed_verification(self, identifier, purpose):
        """Track failed OTP verify attempts. Lockout after limit."""
        fail_key = self._fail_key(identifier, purpose)
        count = cache.get(fail_key, 0) + 1
        cache.set(fail_key, count, timeout=self.VERIFY_FAIL_WINDOW)

        if count >= self.VERIFY_FAIL_LIMIT:
            lockout_key = self._lockout_key(identifier, purpose)
            cache.set(lockout_key, True, timeout=self.LOCKOUT_DURATION)
            return True  # is locked out now

        return False

    def clear_failed_attempts(self, identifier, purpose):
        """Call this on successful verification."""
        cache.delete(self._fail_key(identifier, purpose))
        cache.delete(self._lockout_key(identifier, purpose))


# Single instance — import this everywhere
otp_rate_limiter = OTPRateLimiter()