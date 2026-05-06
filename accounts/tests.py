from django.core import mail
from django.test import TestCase, override_settings
from unittest.mock import Mock, patch

from rest_framework import status
from rest_framework.test import APIClient

from .models import OTP, User
from .services import create_and_send_otp


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class OTPDeliveryTests(TestCase):
    def test_email_otp_is_delivered_when_created(self):
        user = User.objects.create_user(
            username='emailuser',
            email='emailuser@example.com',
            password='Password123',
        )

        otp = create_and_send_otp(
            purpose='REGISTER',
            channel='EMAIL',
            email=user.email,
            user=user,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(otp.otp_code, mail.outbox[0].body)
        self.assertTrue(OTP.objects.filter(pk=otp.pk).exists())

    def test_email_register_api_sends_otp_without_issuing_tokens(self):
        client = APIClient()

        response = client.post('/api/auth/register/', {
            'username': 'apiuser',
            'email': 'apiuser@example.com',
            'password': 'Password123',
            'password2': 'Password123',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('message', response.data)
        self.assertNotIn('access', response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(OTP.objects.filter(email='apiuser@example.com').exists())

    def test_register_api_requires_email_or_phone(self):
        client = APIClient()

        response = client.post('/api/auth/register/', {
            'username': 'missingemail',
            'password': 'Password123',
            'password2': 'Password123',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('At least one of email or phone_number is required.', str(response.data))
        self.assertFalse(User.objects.filter(username='missingemail').exists())

    def test_register_api_uses_email_priority_when_email_and_phone_are_present(self):
        client = APIClient()

        response = client.post('/api/auth/register/', {
            'username': 'bothcontacts',
            'email': 'bothcontacts@example.com',
            'phone_number': '+919876543211',
            'password': 'Password123',
            'password2': 'Password123',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['verification_channel'], 'EMAIL')
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(OTP.objects.filter(email='bothcontacts@example.com').exists())
        self.assertFalse(OTP.objects.filter(phone_number='+919876543211').exists())

    def test_unified_register_uses_email_priority_when_email_and_phone_are_present(self):
        client = APIClient()

        response = client.post('/api/auth/register/unified/', {
            'username': 'unifiedpriority',
            'password': 'Password123',
            'name': 'Unified Priority',
            'date_of_birth': '2000-01-01',
            'gender': 'N',
            'email': 'unifiedpriority@example.com',
            'phone_number': '+919876543214',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['verification_channel'], 'EMAIL')
        self.assertEqual(response.data['channels'], ['email (unifiedpriority@example.com)'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(OTP.objects.filter(email='unifiedpriority@example.com').exists())
        self.assertFalse(OTP.objects.filter(phone_number='+919876543214').exists())


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    TWILIO_ACCOUNT_SID=None,
    TWILIO_AUTH_TOKEN=None,
    TWILIO_PHONE_NUMBER=None,
)
class SMSDeliveryTests(TestCase):
    def test_unified_sms_register_fails_clearly_when_sms_is_not_configured(self):
        client = APIClient()

        response = client.post('/api/auth/register/unified/', {
            'username': 'smsuser',
            'password': 'Password123',
            'name': 'SMS User',
            'date_of_birth': '2000-01-01',
            'gender': 'N',
            'phone_number': '+919876543210',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn('SMS OTP could not be sent', response.data['error'])
        self.assertFalse(User.objects.filter(username='smsuser').exists())


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class BrowserRegistrationFlowTests(TestCase):
    def test_browser_register_verify_then_login_flow(self):
        response = self.client.post('/register/', {
            'username': 'browseruser',
            'email': 'browseruser@example.com',
            'password1': 'StrongPass987!',
            'password2': 'StrongPass987!',
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn('/register/verify/', response['Location'])
        self.assertEqual(len(mail.outbox), 1)

        user = User.objects.get(username='browseruser')
        self.assertFalse(user.is_email_verified)

        otp = OTP.objects.get(email='browseruser@example.com')
        response = self.client.post('/register/verify/', {
            'email': 'browseruser@example.com',
            'otp_code': otp.otp_code,
            'action': 'verify',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)

    def test_browser_login_redirects_unverified_user_to_verify_page(self):
        User.objects.create_user(
            username='unverified',
            email='unverified@example.com',
            password='StrongPass987!',
        )

        response = self.client.post('/login/', {
            'username': 'unverified',
            'password': 'StrongPass987!',
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn('/register/verify/', response['Location'])

    @patch('accounts.services.send_otp_sms_task')
    def test_browser_phone_only_register_verify_flow(self, mock_sms_task):
        mock_sms_task.delay.return_value = Mock(id='sms-task-id')

        response = self.client.post('/register/', {
            'username': 'phonebrowser',
            'phone_number': '+919876543212',
            'password1': 'StrongPass987!',
            'password2': 'StrongPass987!',
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn('/register/verify/', response['Location'])
        self.assertIn('phone_number=%2B919876543212', response['Location'])
        mock_sms_task.delay.assert_called_once()

        otp = OTP.objects.get(phone_number='+919876543212')
        response = self.client.post('/register/verify/', {
            'phone_number': '+919876543212',
            'otp_code': otp.otp_code,
            'action': 'verify',
        })

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='phonebrowser')
        self.assertTrue(user.is_phone_verified)

    def test_profile_update_saves_extended_information(self):
        user = User.objects.create_user(
            username='profileuser',
            email='profileuser@example.com',
            password='StrongPass987!',
            is_email_verified=True,
        )
        self.client.force_login(user)

        response = self.client.post('/profile/', {
            'username': 'profileuser',
            'name': 'Profile User',
            'email': 'profileuser@example.com',
            'phone_number': '+919876543213',
            'date_of_birth': '1999-09-09',
            'gender': 'N',
            'bio': 'Building DevLog.',
        })

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.name, 'Profile User')
        self.assertEqual(user.phone_number, '+919876543213')
        self.assertEqual(user.bio, 'Building DevLog.')
