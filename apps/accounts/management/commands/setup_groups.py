from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create default groups (admin, user) with appropriate permissions"

    def handle(self, *args, **options):
        admin_group, _ = Group.objects.get_or_create(name="admin")
        user_group, _ = Group.objects.get_or_create(name="user")

        all_perms = Permission.objects.all()
        perm_map = {p.codename: p for p in all_perms}

        admin_perms = [
            "can_manage_events",
            "can_manage_guests",
            "can_manage_finance",
            "can_manage_messaging",
            "can_manage_settings",
        ]
        for codename in admin_perms:
            if codename in perm_map:
                admin_group.permissions.add(perm_map[codename])

        user_perms = [
            "can_manage_events",
            "can_manage_guests",
        ]
        for codename in user_perms:
            if codename in perm_map:
                user_group.permissions.add(perm_map[codename])

        self.stdout.write(self.style.SUCCESS("Groups and permissions configured."))
