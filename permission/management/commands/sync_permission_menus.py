from django.core.management.base import BaseCommand

from permission.models import MenuCategory
from permission.services import menu_catalog


class Command(BaseCommand):
    help = 'Create or update the built-in ERP permission menu catalog.'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for code, name in menu_catalog().items():
            menu, created = MenuCategory.objects.update_or_create(
                code=code,
                defaults={'name': name},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'created {menu.code}: {menu.name}'))
            else:
                updated_count += 1
                self.stdout.write(f'updated {menu.code}: {menu.name}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Synced permission menus. created={created_count}, updated={updated_count}'
            )
        )
