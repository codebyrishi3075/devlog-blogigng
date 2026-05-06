from rest_framework import serializers
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """Standard email registration."""
    email = serializers.EmailField(required=True, allow_blank=False)
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def validate_email(self, value):
        value = value.strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def create(self, validated_data):
        validated_data.pop('password2')
        return User.objects.create_user(
            **validated_data,
            is_email_verified=False,
            is_phone_verified=False,
        )


class UnifiedRegisterSerializer(serializers.Serializer):
    """
    New registration serializer.
    email OR phone_number — at least one is mandatory.
    """
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    name = serializers.CharField(max_length=150)
    date_of_birth = serializers.DateField()
    gender = serializers.ChoiceField(choices=['M', 'F', 'O', 'N'])
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(
        max_length=15,
        required=False,
        allow_blank=True
    )

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate_phone_number(self, value):
        if value:
            if not value.startswith('+'):
                raise serializers.ValidationError(
                    "Phone number must be in E.164 format. Example: +919876543210"
                )
            if User.objects.filter(phone_number=value).exists():
                raise serializers.ValidationError(
                    "This phone number is already registered."
                )
        return value

    def validate(self, data):
        email = data.get('email', '').strip()
        phone = data.get('phone_number', '').strip()

        if not email and not phone:
            raise serializers.ValidationError(
                "At least one of email or phone_number is required."
            )
        return data


class UserSerializer(serializers.ModelSerializer):
    is_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'name', 'email',
            'phone_number', 'date_of_birth', 'gender',
            'bio', 'profile_picture',
            'is_email_verified', 'is_phone_verified', 'is_verified'
        ]

    def get_is_verified(self, obj):
        return obj.is_verified()


class MobileRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=15)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_phone_number(self, value):
        if not value.startswith('+'):
            raise serializers.ValidationError(
                "Phone number must be in E.164 format. Example: +919876543210"
            )
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError(
                "This phone number is already registered."
            )
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value


class VerifyOTPSerializer(serializers.Serializer):
    otp_code = serializers.CharField(max_length=6, min_length=6)
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(max_length=15, required=False)
    purpose = serializers.ChoiceField(choices=['REGISTER', 'FORGOT_PASSWORD'])

    def validate(self, data):
        if not data.get('email') and not data.get('phone_number'):
            raise serializers.ValidationError(
                "Provide either email or phone_number."
            )
        return data


class ForgotPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(max_length=15, required=False)

    def validate(self, data):
        if not data.get('email') and not data.get('phone_number'):
            raise serializers.ValidationError(
                "Provide either email or phone_number."
            )
        return data


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(max_length=15, required=False)
    otp_code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if not data.get('email') and not data.get('phone_number'):
            raise serializers.ValidationError(
                "Provide either email or phone_number."
            )
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data
