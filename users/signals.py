from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import social_account_added
from django.dispatch import receiver
from .models import Customer, User

@receiver(user_signed_up)
def user_signed_up_handler(sender, request, user, **kwargs):
    # This signal is triggered for standard allauth sign-ups
    if not hasattr(user, 'customer'):
        Customer.objects.create(user=user)

@receiver(social_account_added)
def social_account_added_handler(sender, request, sociallogin, **kwargs):
    user = sociallogin.user
    # This signal is triggered when a social account is added to an existing user
    if not hasattr(user, 'customer'):
        Customer.objects.create(user=user)

# You may also want to handle the social_account_added signal
# which is more robust for social logins
@receiver(social_account_added)
def social_account_added_handler(sender, request, sociallogin, **kwargs):
    user = sociallogin.user
    if not hasattr(user, 'customer'):
        Customer.objects.create(user=user)