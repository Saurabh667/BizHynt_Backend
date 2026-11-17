from datetime import datetime, timezone, timedelta
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from .models import User


def generate_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=settings.JWT_EXPIRES_DAYS)
    payload = {
        'sub': user_id,
        'iat': int(now.timestamp()),
        'exp': int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm='HS256')


class NestCompatibleJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = get_authorization_header(request).decode('utf-8')
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return None

        token = parts[1]

        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=['HS256'],
                options={'verify_exp': True, 'verify_sub': False}
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired.')
        except Exception as e:
            raise AuthenticationFailed('Invalid authorization token.')

        user_id = payload.get('sub')
        if not user_id:
            raise AuthenticationFailed('Invalid token payload.')

        try:
            user = User.objects.get(id=int(user_id))
        except (User.DoesNotExist, ValueError):
            raise AuthenticationFailed('User not found.')

        if not user.is_active:
            raise AuthenticationFailed('User account is inactive.')

        return (user, token)

    def authenticate_header(self, request):
        return 'Bearer'
