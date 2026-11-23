"""Authenticate API requests with Clerk session tokens.

The frontend sends `Authorization: Bearer <token>`. We verify the token's
signature, expiry and authorized party (the frontend origin) with Clerk's SDK,
then find or create the matching Django user.
"""

from clerk_backend_api.security import TokenVerificationError, VerifyTokenOptions, verify_token
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

User = get_user_model()


class ClerkAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(f"{self.keyword} "):
            # No Clerk token: treat as anonymous. Permission classes then
            # reject the request with 401 unless the view is public.
            return None

        token = header.removeprefix(f"{self.keyword} ").strip()
        if not token:
            raise exceptions.AuthenticationFailed("Missing session token.")

        claims = self.verify(token)
        return (self.get_or_create_user(claims), claims)

    def authenticate_header(self, request):
        # Returning a value here makes DRF answer 401 (not 403) when
        # authentication is missing or fails.
        return self.keyword

    @staticmethod
    def verify(token: str) -> dict:
        try:
            return verify_token(
                token,
                VerifyTokenOptions(
                    secret_key=settings.CLERK_SECRET_KEY,
                    authorized_parties=settings.CLERK_AUTHORIZED_PARTIES,
                ),
            )
        except TokenVerificationError as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired session token.") from exc

    @staticmethod
    def get_or_create_user(claims: dict):
        clerk_id = claims.get("sub")
        if not clerk_id:
            raise exceptions.AuthenticationFailed("Session token has no subject.")

        # First sign-in creates the user with the default Client role (A1).
        user, _ = User.objects.get_or_create(
            clerk_id=clerk_id,
            defaults={"username": clerk_id},
        )
        if not user.is_active:
            raise exceptions.AuthenticationFailed("This account is disabled.")
        return user