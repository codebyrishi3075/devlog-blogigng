from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Show the active email OTP delivery configuration without printing secrets."

    def handle(self, *args, **options):
        required_smtp = {
            'EMAIL_HOST': settings.EMAIL_HOST,
            'EMAIL_HOST_USER': settings.EMAIL_HOST_USER,
            'EMAIL_HOST_PASSWORD': settings.EMAIL_HOST_PASSWORD,
            'DEFAULT_FROM_EMAIL': settings.DEFAULT_FROM_EMAIL,
        }
        missing = [name for name, value in required_smtp.items() if not value]
        using_console = settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend'
        using_smtp = settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'

        self.stdout.write(f"DEBUG: {settings.DEBUG}")
        self.stdout.write(f"EMAIL_DELIVERY_MODE: {getattr(settings, 'EMAIL_DELIVERY_MODE', 'auto')}")
        self.stdout.write(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"EMAIL_HOST: {settings.EMAIL_HOST or '(missing)'}")
        self.stdout.write(f"EMAIL_PORT: {settings.EMAIL_PORT}")
        self.stdout.write(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"EMAIL_USE_SSL: {settings.EMAIL_USE_SSL}")
        self.stdout.write(f"EMAIL_HOST_USER set: {bool(settings.EMAIL_HOST_USER)}")
        self.stdout.write(f"EMAIL_HOST_PASSWORD set: {bool(settings.EMAIL_HOST_PASSWORD)}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL or '(missing)'}")

        if using_console:
            self.stdout.write(self.style.WARNING(
                "Active mode is console email. OTPs will print in the runserver terminal, not reach inbox."
            ))
            self.stdout.write("Set EMAIL_DELIVERY_MODE=smtp and valid SMTP settings in .env for real delivery.")
        elif using_smtp and missing:
            self.stdout.write(self.style.ERROR(
                "SMTP backend is active but required settings are missing: " + ", ".join(missing)
            ))
        elif using_smtp:
            self.stdout.write(self.style.SUCCESS("SMTP backend is active and required settings are present."))
        else:
            self.stdout.write(self.style.WARNING(
                "A custom email backend is active. Verify that it can deliver real emails."
            ))
