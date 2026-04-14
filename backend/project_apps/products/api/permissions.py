from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsAdminOrReadOnly(BasePermission):
    """
    Allow read-only access to anyone,
    but write access only to admin users.
    """

    def has_permission(self, request, view):
        # Allow GET, HEAD, OPTIONS for everyone
        if request.method in SAFE_METHODS:
            return True

        # Only admin users can modify
        return request.user and request.user.is_staff
    


class IsOwnerOrReadOnly(BasePermission):
    
    def has_object_permission(self, request, view, obj):
        # Allow read-only methods
        if request.method in SAFE_METHODS:
            return True
        
        # Allow write only if user is owner
        return obj.user == request.user