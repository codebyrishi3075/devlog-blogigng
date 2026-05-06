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
            email = user.email.strip()
            phone_number = (user.phone_number or '').strip()
            otp_channel = 'EMAIL' if email else 'SMS'
            otp_destination = email or phone_number
            try:
                create_and_send_otp(
                    purpose='REGISTER',
                    channel=otp_channel,
                    email=email or None,
                    phone_number=None if email else phone_number,
                    user=user,
                )
            except Exception as exc:
                user.delete()
                messages.error(request, f'Registration failed because OTP could not be sent: {exc}')
            else:
                messages.success(
                    request,
                    f'Registration successful, {user.username}! OTP sent to {otp_destination}. Please verify before login.'
                )
                query = {'email': email} if email else {'phone_number': phone_number}
                verify_url = f"{reverse('verify_registration')}?{urlencode(query)}"
                return redirect(verify_url)
    
    return render(request, 'accounts/register.html', {'form': form})


def verify_registration_view(request):
    if request.user.is_authenticated and request.user.is_verified():
        return redirect('home')

    initial_email = request.GET.get('email') or request.POST.get('email') or ''
    initial_phone = request.GET.get('phone_number') or request.POST.get('phone_number') or ''
    form = VerifyOTPForm(initial={'email': initial_email, 'phone_number': initial_phone})

    if request.method == 'POST':
        action = request.POST.get('action', 'verify')
        form = VerifyOTPForm(request.POST)

        if action == 'resend':
            email = request.POST.get('email', '').strip()
            phone_number = request.POST.get('phone_number', '').strip()
            if not email and not phone_number:
                messages.error(request, 'Enter your email or mobile number to resend OTP.')
            else:
                try:
                    if email:
                        user = User.objects.get(email=email)
                    else:
                        user = User.objects.get(phone_number=phone_number)
                    create_and_send_otp(
                        purpose='REGISTER',
                        channel='EMAIL' if email else 'SMS',
                        email=email or None,
                        phone_number=None if email else phone_number,
                        user=user,
                    )
                    messages.success(request, f'A new OTP has been sent to {email or phone_number}.')
                except User.DoesNotExist:
                    messages.error(request, 'No account found for this contact.')
                except Exception as exc:
                    messages.error(request, f'Could not resend OTP: {exc}')
            return render(request, 'accounts/verify_registration.html', {'form': form})

        if form.is_valid():
            email = form.cleaned_data['email']
            phone_number = form.cleaned_data['phone_number']
            otp_code = form.cleaned_data['otp_code']
            success, message, otp = verify_otp(
                purpose='REGISTER',
                otp_code=otp_code,
                email=email or None,
                phone_number=None if email else phone_number,
            )

            if success:
                user = otp.user
                if email:
                    user.is_email_verified = True
                    user.save(update_fields=['is_email_verified'])
                else:
                    user.is_phone_verified = True
                    user.save(update_fields=['is_phone_verified'])
                login(request, user)
                messages.success(request, 'Account verified successfully. Welcome to DevLog!')
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
                    query = {'email': user.email} if user.email else {'phone_number': user.phone_number}
                    verify_url = f"{reverse('verify_registration')}?{urlencode(query)}"
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
