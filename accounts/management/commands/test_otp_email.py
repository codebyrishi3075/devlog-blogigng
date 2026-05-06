from django.core.management.base import BaseCommand, CommandError

from accounts.tasks import send_otp_email_sync, send_otp_email_task


class Command(BaseCommand):
    help = "Send a test OTP email directly and through Celery."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            required=True,
            help="Email address that should receive the test OTP.",
        )

    def handle(self, *args, **options):
        email = options["email"]
        otp_code = "123456"
        purpose = "REGISTER"

        self.stdout.write(f"Sending synchronous test OTP to {email}...")
        try:
            sent_count = send_otp_email_sync(email, otp_code, purpose)
        except Exception as exc:
            raise CommandError(f"Synchronous OTP email failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Synchronous send result: {sent_count}"))

        self.stdout.write(f"Queueing Celery test OTP to {email}...")
        try:
            result = send_otp_email_task.delay(email, otp_code, purpose)
        except Exception as exc:
            raise CommandError(f"Celery OTP email enqueue failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Celery task queued: {result.id}"))
        self.stdout.write(
            "Watch the Celery worker terminal for [OTP EMAIL TASK] logs and the OTP."
        )
