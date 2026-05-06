from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone

from .models import User, OTP
from .serializers import (
    RegisterSerializer, UserSerializer,
    UnifiedRegisterSerializer,
    MobileRegisterSerializer, VerifyOTPSerializer,
    ForgotPasswordRequestSerializer, ResetPasswordSerializer
)
from .services import create_and_send_otp, verify_otp


class RegisterAPIView(APIView):
    """Original email-only registration — kept for backward compat."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            try:
                create_and_send_otp(
                    purpose='REGISTER',
                    channel='EMAIL',
                    email=user.email,
                    user=user,
                )
            except Exception as e:
                user.delete()
                return Response(
                    {'error': f'Account was not created because email OTP could not be sent: {e}'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            return Response({
                'message': f'OTP sent to email ({user.email}). Verify to activate your account.',
                'user': UserSerializer(user).data,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UnifiedRegisterAPIView(APIView):
    """
    Step 1 — Registration.
    Accepts name, DOB, gender, username, password.
    Email OR phone (at least one mandatory).
    Creates user as unverified, sends OTP on provided channel(s).
    User cannot access protected routes until verified.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UnifiedRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email = data.get('email', '').strip() or None
        phone_number = data.get('phone_number', '').strip() or None

        # Create user — unverified state
        user = User.objects.create_user(
            username=data['username'],
            password=data['password'],
            name=data['name'],
            date_of_birth=data['date_of_birth'],
            gender=data['gender'],
            email=email or '',
            phone_number=phone_number,
            is_email_verified=False,
            is_phone_verified=False,
        )

        sent_channels = []

        # Send OTP on email if provided
        if email:
            try:
                create_and_send_otp(
                    purpose='REGISTER',
                    channel='EMAIL',
                    email=email,
                    user=user,
                )
                sent_channels.append(f"email ({email})")
            except PermissionError as e:
                user.delete()
                return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            except Exception as e:
                user.delete()
                return Response(
                    {'error': f'Account was not created because email OTP could not be sent: {e}'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

        # Send OTP on phone if provided
        if phone_number:
            try:
                create_and_send_otp(
                    purpose='REGISTER',
                    channel='SMS',
                    phone_number=phone_number,
                    user=user,
                )
                sent_channels.append(f"SMS ({phone_number})")
            except PermissionError as e:
                # Email OTP already sent — don't delete user, just warn
                return Response({
                    'message': f'Account created. Email OTP sent but SMS failed: {str(e)}',
                    'user_id': user.id,
                }, status=status.HTTP_200_OK)
            except Exception as e:
                if not sent_channels:
                    user.delete()
                    return Response(
                        {'error': f'Account was not created because SMS OTP could not be sent: {e}'},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE
                    )
                return Response({
                    'message': f'Account created. {", ".join(sent_channels)} OTP sent but SMS failed: {e}',
                    'user_id': user.id,
                    'channels': sent_channels,
                }, status=status.HTTP_200_OK)

        return Response({
            'message': f"OTP sent to: {', '.join(sent_channels)}. Verify to activate your account.",
            'user_id': user.id,
            'channels': sent_channels,
        }, status=status.HTTP_201_CREATED)


class VerifyRegistrationOTPAPIView(APIView):
    """
    Step 2 — OTP Verification after registration.
    Marks email or phone as verified.
    Returns JWT only after verification.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        otp_code = request.data.get('otp_code')
        email = request.data.get('email')
        phone_number = request.data.get('phone_number')

        if not otp_code:
            return Response(
                {'error': 'otp_code is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not email and not phone_number:
            return Response(
                {'error': 'Provide either email or phone_number.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        success, message, otp = verify_otp(
            purpose='REGISTER',
            otp_code=otp_code,
            email=email,
            phone_number=phone_number,
        )

        if not success:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

        # Mark appropriate channel as verified
        user = otp.user
        if email:
            user.is_email_verified = True
        if phone_number:
            user.is_phone_verified = True
        user.save()

        # Issue JWT now that user is verified
        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Account verified successfully. Welcome to DevLog!',
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_200_OK)


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)

        if not user:
            return Response(
                {'error': 'Invalid credentials.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Block unverified users
        if not user.is_verified():
            return Response(
                {
                    'error': 'Account not verified.',
                    'detail': 'Please verify your email or phone number before logging in.',
                    'is_email_verified': user.is_email_verified,
                    'is_phone_verified': user.is_phone_verified,
                },
                status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class MobileRegisterAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MobileRegisterSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            try:
                create_and_send_otp(
                    purpose='REGISTER',
                    channel='SMS',
                    phone_number=data['phone_number'],
                )
            except PermissionError as e:
                return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            except Exception as e:
                return Response(
                    {'error': f'SMS OTP could not be sent: {e}'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            return Response(
                {'message': f"OTP sent to {data['phone_number']}."},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyMobileOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone_number = request.data.get('phone_number')
        otp_code = request.data.get('otp_code')
        username = request.data.get('username')
        password = request.data.get('password')

        if not all([phone_number, otp_code, username, password]):
            return Response(
                {'error': 'phone_number, otp_code, username, password all required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        success, message, otp = verify_otp(
            purpose='REGISTER',
            otp_code=otp_code,
            phone_number=phone_number,
        )

        if not success:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response(
                {'error': 'Username already taken.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.create_user(
            username=username,
            password=password,
            phone_number=phone_number,
            is_phone_verified=True,
        )
        otp.user = user
        otp.save()

        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Registration successful.',
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)


class ForgotPasswordRequestAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email = data.get('email')
        phone_number = data.get('phone_number')

        try:
            user = User.objects.get(email=email) if email else User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return Response(
                {'message': 'If this account exists, an OTP has been sent.'},
                status=status.HTTP_200_OK
            )

        channel = 'EMAIL' if email else 'SMS'
        try:
            create_and_send_otp(
                purpose='FORGOT_PASSWORD',
                channel=channel,
                email=email,
                phone_number=phone_number,
                user=user,
            )
        except PermissionError as e:
            return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except Exception as e:
            return Response(
                {'error': f'OTP could not be sent: {e}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return Response(
            {'message': 'If this account exists, an OTP has been sent.'},
            status=status.HTTP_200_OK
        )


class VerifyForgotPasswordOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(
            data={**request.data, 'purpose': 'FORGOT_PASSWORD'}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        success, message, _ = verify_otp(
            purpose='FORGOT_PASSWORD',
            otp_code=data['otp_code'],
            email=data.get('email'),
            phone_number=data.get('phone_number'),
        )

        if not success:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': message}, status=status.HTTP_200_OK)


class ResetPasswordAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email = data.get('email')
        phone_number = data.get('phone_number')

        try:
            filters = {
                'purpose': 'FORGOT_PASSWORD',
                'otp_code': data['otp_code'],
                'is_verified': True,
            }
            if email:
                filters['email'] = email
            else:
                filters['phone_number'] = phone_number
            otp = OTP.objects.get(**filters)
        except OTP.DoesNotExist:
            return Response(
                {'error': 'Invalid or unverified OTP.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from datetime import timedelta
        if timezone.now() > otp.created_at + timedelta(minutes=15):
            return Response(
                {'error': 'OTP session expired. Please restart.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = otp.user
        user.set_password(data['new_password'])
        user.save()
        otp.delete()

        return Response(
            {'message': 'Password reset successful.'},
            status=status.HTTP_200_OK
        )


class ResendOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        purpose = request.data.get('purpose')
        email = request.data.get('email')
        phone_number = request.data.get('phone_number')

        if purpose not in ['REGISTER', 'FORGOT_PASSWORD']:
            return Response(
                {'error': "purpose must be 'REGISTER' or 'FORGOT_PASSWORD'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not email and not phone_number:
            return Response(
                {'error': 'Provide either email or phone_number.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = None
        if purpose == 'FORGOT_PASSWORD':
            try:
                user = User.objects.get(email=email) if email else User.objects.get(phone_number=phone_number)
            except User.DoesNotExist:
                return Response(
                    {'message': 'If this account exists, an OTP has been sent.'},
                    status=status.HTTP_200_OK
                )

        channel = 'EMAIL' if email else 'SMS'
        try:
            create_and_send_otp(
                purpose=purpose,
                channel=channel,
                email=email,
                phone_number=phone_number,
                user=user,
            )
        except PermissionError as e:
            return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except Exception as e:
            return Response(
                {'error': f'OTP could not be sent: {e}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return Response({'message': 'A new OTP has been sent.'}, status=status.HTTP_200_OK)
