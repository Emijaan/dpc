from django.conf import settings
from django.core.management.base import BaseCommand

from commands import signing


class Command(BaseCommand):
    help = "Generate the command signing key (if missing) and print the public key for the Android app."

    def handle(self, *args, **options):
        from pathlib import Path
        if not Path(settings.SIGNING_KEY_PATH).exists():
            signing.generate_key(settings.SIGNING_KEY_PATH)
            self.stdout.write(f"Created {settings.SIGNING_KEY_PATH}")
        self.stdout.write("PUBLIC KEY (base64 X.509 DER):")
        self.stdout.write(signing.public_key_b64())

