from django.core.management.base import BaseCommand

from users.models import User
from notifications.models import Notification
from notifications.notifications_service import create_notification


class Command(BaseCommand):
    help = "Debug the notifications system by creating a test notification and inspecting results"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            default=False,
            help="Delete all existing notifications before the test",
        )
        parser.add_argument(
            "--email",
            type=str,
            default=None,
            help="Specific user email to send the test notification to (default: first DRIVER role)",
        )
        parser.add_argument(
            "--role",
            type=str,
            choices=[r for r, _ in User.Role.choices],
            default=User.Role.DRIVER,
            help="Role of the user to pick when --email is not used",
        )

    def handle(self, *args, **options):
        clear_first = options["clear"]
        target_email = options["email"]
        target_role = options["role"]

        self.stdout.write("Debugging notification system...")

        if target_email:
            test_user = User.objects.filter(email=target_email).first()
            if not test_user:
                self.stdout.write(
                    self.style.ERROR(f'No user found with email "{target_email}".')
                )
                return
        else:
            test_user = User.objects.filter(role=target_role).first()
            if not test_user:
                self.stdout.write(
                    self.style.ERROR(
                        f'No user found with role "{target_role}". Seed the database first.'
                    )
                )
                return

        self.stdout.write(f"Test user: {test_user.get_full_name()} <{test_user.email}>")

        if clear_first:
            deleted, _ = Notification.objects.all().delete()
            self.stdout.write(f"Cleared {deleted} existing notification(s).")

        try:
            self.stdout.write("\nTesting create_notification function...")

            result = create_notification(
                recipient=test_user,
                title="Test Notification",
                message="This is a test notification message.",
            )

            self.stdout.write(f"create_notification returned: {result}")

            notifications = Notification.objects.filter(recipient=test_user)
            self.stdout.write(
                f"Notifications in database for user: {notifications.count()}"
            )

            for notification in notifications:
                self.stdout.write(f"  - Title: {notification.title}")
                self.stdout.write(f"    Message: {notification.message}")
                self.stdout.write(f"    Created: {notification.created_at}")
                self.stdout.write(f"    Is read: {notification.is_read}")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"ERROR: create_notification test failed: {e}")
            )
            import traceback

            traceback.print_exc()

        self.stdout.write(self.style.SUCCESS("\nNotification debugging completed!"))
