from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from notifications.models import Notification
from notifications.serializers import NotificationSerializer


def create_notification(
    recipient,
    title,
    message,
    delivery=None,
    notification_type=None,
    bid_request=None,
    bid=None,
    link_path="",
):
    if notification_type is None:
        notification_type = Notification.Type.GENERAL

    notification = Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        delivery=delivery,
        notification_type=notification_type,
        bid_request=bid_request,
        bid=bid,
        link_path=link_path or "",
    )

    try:
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            payload = NotificationSerializer(notification).data
            async_to_sync(channel_layer.group_send)(
                f"user_{recipient.id}",
                {
                    "type": "notification_send",
                    "data": payload,
                },
            )
    except Exception:
        pass

    return notification
