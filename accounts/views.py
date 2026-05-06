from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.urls import reverse
from urllib.parse import urlencode

from .forms import RegisterForm, LoginForm, ProfileUpdateForm, VerifyOTPForm
from django.contrib.auth.decorators import login_required
from .models import User
from .services import create_and_send_otp, verify_otp


def home_view(request):
    return render(request, 'home.html')

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    form = RegisterForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.save()
            try:
                create_and_send_otp(
                    purpose='REGISTER',
                    channel='EMAIL',
                    email=user.email,
                    user=user,
                )
            except Exception as exc:
                user.delete()
                messages.error(request, f'Registration failed because OTP could not be sent: {exc}')
            else:
                messages.success(
                    request,
                    f'Registration successful, {user.username}! OTP sent to {user.email}. Please verify before login.'
                )
                verify_url = f"{reverse('verify_registration')}?{urlencode({'email': user.email})}"
                return redirect(verify_url)
    
    return render(request, 'accounts/register.html', {'form': form})


def verify_registration_view(request):
    if request.user.is_authenticated and request.user.is_verified():
        return redirect('home')

    initial_email = request.GET.get('email') or request.POST.get('email') or ''
    form = VerifyOTPForm(initial={'email': initial_email})

    if request.method == 'POST':
        action = request.POST.get('action', 'verify')
        form = VerifyOTPForm(request.POST)

        if action == 'resend':
            email = request.POST.get('email', '').strip()
            if not email:
                messages.error(request, 'Enter your email address to resend OTP.')
            else:
                try:
                    user = User.objects.get(email=email)
                    create_and_send_otp(
                        purpose='REGISTER',
                        channel='EMAIL',
                        email=email,
                        user=user,
                    )
                    messages.success(request, f'A new OTP has been sent to {email}.')
                except User.DoesNotExist:
                    messages.error(request, 'No account found for this email.')
                except Exception as exc:
                    messages.error(request, f'Could not resend OTP: {exc}')
            return render(request, 'accounts/verify_registration.html', {'form': form})

        if form.is_valid():
            email = form.cleaned_data['email']
            otp_code = form.cleaned_data['otp_code']
            success, message, otp = verify_otp(
                purpose='REGISTER',
                otp_code=otp_code,
                email=email,
            )

            if success:
                user = otp.user
                user.is_email_verified = True
                user.save(update_fields=['is_email_verified'])
                login(request, user)
                messages.success(request, 'Email verified successfully. Welcome to DevLog!')
                return redirect('home')

            messages.error(request, message)

    return render(request, 'accounts/verify_registration.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                if not user.is_verified():
                    verify_url = f"{reverse('verify_registration')}?{urlencode({'email': user.email})}"
                    messages.error(request, 'Please verify your email or phone number before logging in.')
                    return redirect(verify_url)
                login(request, user)
                messages.success(request, f'Login successful, {user.username}!')
                return redirect('home')
            else:
                messages.error(request, 'Invalid username or password.')
    
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)  # Ensure any existing session is cleared
    messages.info(request, 'You have been logged out. Please log in again.')
    return redirect('login')


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
            
    return render(request, 'accounts/profile.html', {'form': form})
