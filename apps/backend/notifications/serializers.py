from rest_framework import serializers

from notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    delivery_id = serializers.CharField(
        source="delivery.public_id", read_only=True, allow_null=True
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "delivery_id",
            "notification_type",
            "link_path",
            "bid_request",
            "bid",
            "is_read",
            "created_at",
        ]
