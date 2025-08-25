from rest_framework.permissions import BasePermission


# 권한 클래스
class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.user_role == "admin"


class IsUserRole(BasePermission):
    allowed_roles = ["admin", "customer"]

    def has_permission(self, request, view):
        return request.user and request.user.user_role in self.allowed_roles


class IsOwnerRole(BasePermission):
    allowed_roles = ["admin", "owner"]

    def has_permission(self, request, view):
        return request.user and request.user.user_role in self.allowed_roles
