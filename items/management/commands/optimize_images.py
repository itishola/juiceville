# management/commands/optimize_images.py
from django.core.management.base import BaseCommand
from PIL import Image
from items.models import Item
import os

class Command(BaseCommand):
    def handle(self, *args, **options):
        for item in Item.objects.exclude(image__isnull=True).exclude(image=''):
            try:
                img_path = item.image.path
                with Image.open(img_path) as img:
                    # Resize if too large
                    if img.size[0] > 800 or img.size[1] > 800:
                        img.thumbnail((800, 800), Image.Resampling.LANCZOS)
                        img.save(img_path, optimize=True, quality=85)
                        self.stdout.write(f"Optimized: {item.name}")
            except Exception as e:
                self.stdout.write(f"Error with {item.name}: {str(e)}")