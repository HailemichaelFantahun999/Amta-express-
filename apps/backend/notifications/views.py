from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from notifications.models import Notification
from notifications.serializers import NotificationSerializer


class NotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user).order_by(
            "-created_at"
        )[:20]
        return Response(NotificationSerializer(notifications, many=True).data)

    def patch(self, request):
        ids = request.data.get("ids")
        if ids is not None:
            if not isinstance(ids, list) or not ids:
                return Response(
                    {"detail": "ids must be a non-empty list."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            notifications = Notification.objects.filter(
                recipient=request.user, pk__in=ids, is_read=False
            )
        else:
            notifications = Notification.objects.filter(
                recipient=request.user, is_read=False
            )
        marked = 0
        for notification in notifications:
            notification.mark_read()
            marked += 1
        return Response({"detail": f"{marked} notification(s) marked as read."})
