from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import User
from vehicles.models import Vehicle, VehicleCategory
from vehicles.serializers import VehicleCategorySerializer, VehicleSerializer


class VehicleViewSet(viewsets.ModelViewSet):
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]
    queryset = Vehicle.objects.select_related("assigned_driver", "category").order_by(
        "identifier"
    )

    def create(self, request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            return Response(
                {"detail": "Only admins can create vehicles."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)


class VehicleCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = VehicleCategorySerializer
    permission_classes = [IsAuthenticated]
    queryset = VehicleCategory.objects.order_by("name")

    def create(self, request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            return Response(
                {"detail": "Only admins can create vehicle categories."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)
