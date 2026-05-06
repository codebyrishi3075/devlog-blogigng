from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import random


class User(AbstractUser):

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
        ('N', 'Prefer not to say'),
    ]

    # Extended profile fields
    name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True
    )
    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        unique=True
    )
    bio = models.TextField(blank=True)
    profile_picture = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True
    )

    # Verification flags
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    def is_verified(self):
        """User can access app only if at least one channel is verified."""
        return self.is_email_verified or self.is_phone_verified

    def __str__(self):
        return self.username


class OTP(models.Model):

    PURPOSE_CHOICES = [
        ('REGISTER', 'Register'),
        ('FORGOT_PASSWORD', 'Forgot Password'),
    ]

    CHANNEL_CHOICES = [
        ('EMAIL', 'Email'),
        ('SMS', 'SMS'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='otps'
    )
    email = models.EmailField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def is_expired(self):
        return timezone.now() > self.expires_at

    @staticmethod
    def generate_otp():
        return str(random.randint(100000, 999999))

    def __str__(self):
        identifier = self.email or self.phone_number
        return f"{self.purpose} OTP for {identifier}"