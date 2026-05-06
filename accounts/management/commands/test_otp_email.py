from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from accounts.tasks import send_otp_email_sync, send_otp_email_task


class Command(BaseCommand):
    help = "Send a test OTP email directly and through Celery."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            required=True,
            help="Email address that should receive the test OTP.",
        )
        parser.add_argument(
            "--celery",
            action="store_true",
            help="Also send through the Celery task path. Local eager mode runs it immediately.",
        )

    def handle(self, *args, **options):
        email = options["email"]
        otp_code = "123456"
        purpose = "REGISTER"

        self.stdout.write(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"EMAIL_HOST: {settings.EMAIL_HOST or '(missing)'}")
        self.stdout.write(f"EMAIL_HOST_USER set: {bool(settings.EMAIL_HOST_USER)}")
        self.stdout.write(f"EMAIL_HOST_PASSWORD set: {bool(settings.EMAIL_HOST_PASSWORD)}")

        self.stdout.write(f"Sending synchronous test OTP to {email}...")
        try:
            sent_count = send_otp_email_sync(email, otp_code, purpose)
        except Exception as exc:
            raise CommandError(f"Synchronous OTP email failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Synchronous send result: {sent_count}"))

        if options["celery"]:
            self.stdout.write(f"Sending Celery task test OTP to {email}...")
            try:
                result = send_otp_email_task.delay(email, otp_code, purpose)
            except Exception as exc:
                raise CommandError(f"Celery OTP email failed: {exc}") from exc

            self.stdout.write(self.style.SUCCESS(f"Celery task result id: {result.id}"))
