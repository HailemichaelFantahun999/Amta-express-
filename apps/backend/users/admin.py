from django.contrib import admin

from users.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "first_name",
        "last_name",
        "role",
        "status",
        "last_active_at",
    )
    search_fields = ("email", "first_name", "last_name", "phone")
    list_filter = ("role", "status")
