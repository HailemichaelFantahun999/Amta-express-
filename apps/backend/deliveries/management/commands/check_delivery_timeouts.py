from django.core.management.base import BaseCommand
from deliveries.assignment import check_and_reassign_timeout_deliveries


class Command(BaseCommand):
    help = "Check for delivery timeouts and reassign to next available drivers"

    def handle(self, *args, **options):
        self.stdout.write("Checking for delivery timeouts...")

        try:
            count = check_and_reassign_timeout_deliveries()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully processed {count} timeout reassignments"
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error checking timeouts: {e}"))
