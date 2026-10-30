from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return

        for address in sociallogin.email_addresses:
            if not address.verified:
                continue
            user = (
                get_user_model()
                .objects.filter(email__iexact=address.email)
                .first()
            )
            if not user:
                continue
            email_address, _ = EmailAddress.objects.get_or_create(
                user=user,
                email=address.email.lower(),
            )
            email_address.set_verified()
            if not email_address.primary:
                email_address.set_as_primary()
            sociallogin.connect(request, user)
            return
