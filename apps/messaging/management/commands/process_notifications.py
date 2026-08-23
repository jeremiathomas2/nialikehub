from django.core.management.base import BaseCommand

from apps.messaging.services import process_queue


class Command(BaseCommand):
    help = "Process the notification queue (replaces cron/worker.php). Run every minute."

    def handle(self, *args, **options):
        result = process_queue()
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {result['processed']} jobs — sent: {result['sent']}, failed: {result['failed']}"
            )
        )
