from rest_framework.permissions import BasePermission


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, 'is_authenticated', False))


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            getattr(request.user, 'is_authenticated', False) and
            getattr(request.user, 'role', None) in ['super_admin', 'admin']
        )


class IsSuperAdminUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            getattr(request.user, 'is_authenticated', False) and
            getattr(request.user, 'role', None) == 'super_admin'
        )
