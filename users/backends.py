from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        try:
            # Try to find user by username or email (case-insensitive)
            user = UserModel.objects.get(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
        except UserModel.DoesNotExist:
            return None
        except UserModel.MultipleObjectsReturned:
            # If multiple users found, try username first, then email
            try:
                user = UserModel.objects.get(username__iexact=username)
            except UserModel.DoesNotExist:
                try:
                    user = UserModel.objects.get(email__iexact=username)
                except UserModel.DoesNotExist:
                    return None
        
        if user.check_password(password):
            return user
        return None