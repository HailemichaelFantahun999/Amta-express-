from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.backends import TokenBackend

User = get_user_model()


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query = self.scope.get("query_string", b"").decode()
        params = parse_qs(query)
        token = params.get("token", [None])[0]
        if not token:
            await self.close()
            return
        try:
            tb = TokenBackend(algorithm="HS256", signing_key=settings.SECRET_KEY)
            data = tb.decode(token)
            user_id = data.get("user_id") or data.get("user_id")
            user = await sync_to_async(User.objects.get)(pk=user_id)
            self.user = user
        except Exception:
            await self.close()
            return

        self.group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_send(self, event):
        await self.send_json(
            {"type": "notification", "notification": event.get("data")}
        )
