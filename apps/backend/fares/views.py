from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from fares.models import FareSettings
from fares.serializers import FareRuleSerializer, FareSettingsSerializer


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def fare_settings(request):
    if request.method == "GET":
        settings_obj = FareSettings.get_solo()
        serializer = FareSettingsSerializer(settings_obj)
        return Response(serializer.data)

    settings_obj = FareSettings.get_solo()
    serializer = FareSettingsSerializer(settings_obj, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(
        {
            "message": "Fare settings updated successfully",
            "settings": serializer.data,
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def fare_rules(request):
    if request.method == "GET":
        rules = [
            {
                "id": 1,
                "name": "Standard Rate",
                "min_distance": 0,
                "max_distance": 10,
                "rate": 15.00,
                "active": True,
            },
            {
                "id": 2,
                "name": "Long Distance Rate",
                "min_distance": 10,
                "max_distance": 50,
                "rate": 12.00,
                "active": True,
            },
        ]
        return Response(rules)

    elif request.method == "POST":
        serializer = FareRuleSerializer(data=request.data)
        if serializer.is_valid():
            return Response(
                {
                    "message": "Fare rule created successfully",
                    "rule": serializer.validated_data,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
