from django.urls import path
from . import views
from .api_views import (
    RegisterAPIView, UnifiedRegisterAPIView, VerifyRegistrationOTPAPIView,
    LoginAPIView, MeAPIView,
    MobileRegisterAPIView, VerifyMobileOTPAPIView,
    ForgotPasswordRequestAPIView, VerifyForgotPasswordOTPAPIView,
    ResetPasswordAPIView, ResendOTPAPIView,
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # Template URLs
    path('register/', views.register_view, name='register'),
    path('register/verify/', views.verify_registration_view, name='verify_registration'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('', views.home_view, name='home'),

    # Core Auth
    path('api/auth/register/', RegisterAPIView.as_view()),
    path('api/auth/register/unified/', UnifiedRegisterAPIView.as_view()),
    path('api/auth/register/verify/', VerifyRegistrationOTPAPIView.as_view()),
    path('api/auth/login/', LoginAPIView.as_view()),
    path('api/auth/me/', MeAPIView.as_view()),
    path('api/auth/token/refresh/', TokenRefreshView.as_view()),

    # Mobile Registration
    path('api/auth/register/mobile/', MobileRegisterAPIView.as_view()),
    path('api/auth/register/mobile/verify/', VerifyMobileOTPAPIView.as_view()),

    # Forgot Password
    path('api/auth/forgot-password/', ForgotPasswordRequestAPIView.as_view()),
    path('api/auth/forgot-password/verify-otp/', VerifyForgotPasswordOTPAPIView.as_view()),
    path('api/auth/forgot-password/reset/', ResetPasswordAPIView.as_view()),

    # Resend OTP
    path('api/auth/otp/resend/', ResendOTPAPIView.as_view()),
]
