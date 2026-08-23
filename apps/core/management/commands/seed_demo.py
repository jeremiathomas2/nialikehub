"""
Seed the database with realistic demo data.

Usage:
    python manage.py seed_demo           # create demo data (skips what already exists)
    python manage.py seed_demo --flush   # delete previously seeded demo data first
"""
import random
from datetime import timedelta, date, time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import AuditLog
from apps.events.models import Event, Guest
from apps.finance.models import Pledge, Payment
from apps.messaging.models import MessageTemplate, MessageLog, WhatsAppCard

DEMO_PASSWORD = "Demo@1234"

USERS = [
    {"name": "Amina Hassan", "email": "amina@demo.nialike.test", "role": User.Role.USER,
     "status": User.Status.APPROVED, "phone": "0712000001"},
    {"name": "Joseph Mwakalinga", "email": "joseph@demo.nialike.test", "role": User.Role.USER,
     "status": User.Status.APPROVED, "phone": "0712000002"},
    {"name": "Grace Peter", "email": "grace@demo.nialike.test", "role": User.Role.USER,
     "status": User.Status.PENDING, "phone": "0712000003"},
    {"name": "Daniel John", "email": "daniel@demo.nialike.test", "role": User.Role.USER,
     "status": User.Status.SUSPENDED, "phone": "0712000004"},
]

EVENTS = [
    {
        "owner": "amina@demo.nialike.test", "title": "Amina & David Wedding",
        "event_type": "Wedding", "status": Event.Status.PUBLISHED, "days": 32,
        "start_time": time(10, 0), "end_time": time(16, 0),
        "venue": "Golden Rose Gardens", "address": "Bagamoyo Rd, Dar es Salaam",
        "description": ("Join us as we celebrate the union of Amina & David. "
                        "Ceremony at 10:00, reception to follow."),
        "guests": [
            ("Neema Mushi", "Family", Guest.InvitationStatus.RSVP_YES),
            ("Baraka Okonkwo", "Friends", Guest.InvitationStatus.VIEWED),
            ("Salma Juma", "Friends", Guest.InvitationStatus.SENT),
            ("Peter Msigwa", "Colleagues", Guest.InvitationStatus.CHECKED_IN),
            ("Joyce Kimaro", "Family", Guest.InvitationStatus.DELIVERED),
            ("Emmanuel Sengo", "Church", Guest.InvitationStatus.PENDING),
            ("Fatuma Ally", "Colleagues", Guest.InvitationStatus.RSVP_YES),
            ("Michael Komba", "Friends", Guest.InvitationStatus.RSVP_NO),
        ],
        "cards": [
            ("Wedding Classic", WhatsAppCard.Style.CLASSIC, "Amina & David", True),
            ("Elegant Minimal", WhatsAppCard.Style.MINIMAL, "You are invited", False),
            ("Royal Gold", WhatsAppCard.Style.ROYAL, "A Royal Celebration", False),
        ],
        "pledges": [
            (250_000, 250_000, Pledge.Status.PAID, -5),
            (150_000, 80_000, Pledge.Status.PARTIAL, 10),
            (500_000, 500_000, Pledge.Status.PAID, -2),
            (100_000, 0, Pledge.Status.PROMISED, 20),
            (300_000, 120_000, Pledge.Status.PARTIAL, 15),
            (75_000, 0, Pledge.Status.DEFAULTED, -7),
        ],
    },
    {
        "owner": "amina@demo.nialike.test", "title": "Baby Shower — Neema",
        "event_type": "Baby Shower", "status": Event.Status.PUBLISHED, "days": 14,
        "start_time": time(14, 0), "end_time": time(18, 0),
        "venue": "Mikocheni Garden", "address": "Mikocheni B, Dar es Salaam",
        "description": "A sweet afternoon celebrating baby Neema on the way.",
        "guests": [
            ("Hawa Mwinyi", "Family", Guest.InvitationStatus.RSVP_YES),
            ("Zawadi Nyerere", "Friends", Guest.InvitationStatus.SENT),
            ("Anna Macha", "Church", Guest.InvitationStatus.VIEWED),
            ("Rehema Simba", "Family", Guest.InvitationStatus.RSVP_YES),
            ("Upendo Charles", "Friends", Guest.InvitationStatus.PENDING),
        ],
        "cards": [("Shower Minimal", WhatsAppCard.Style.MINIMAL, "Baby Neema Shower", True)],
        "pledges": [
            (50_000, 50_000, Pledge.Status.PAID, 3),
            (120_000, 40_000, Pledge.Status.PARTIAL, 9),
            (30_000, 0, Pledge.Status.PROMISED, 12),
        ],
    },
    {
        "owner": "joseph@demo.nialike.test", "title": "Mzee Komba 70th Birthday",
        "event_type": "Birthday", "status": Event.Status.DRAFT, "days": 60,
        "start_time": time(11, 0), "end_time": None,
        "venue": "Komba Family Residence", "address": "Morogoro",
        "description": "Seven decades of blessings — draft plans in progress.",
        "guests": [
            ("Elias Komba", "Family", Guest.InvitationStatus.PENDING),
            ("Mama Lidia", "Family", Guest.InvitationStatus.PENDING),
            ("Robert Nkya", "Friends", Guest.InvitationStatus.PENDING),
        ],
        "cards": [], "pledges": [],
    },
    {
        "owner": "joseph@demo.nialike.test", "title": "Graduation Party — Baraka",
        "event_type": "Graduation", "status": Event.Status.CLOSED, "days": -21,
        "start_time": time(16, 0), "end_time": time(22, 0),
        "venue": "New Africa Hall", "address": "Arusha",
        "description": "Celebrating Baraka's BSc. Civil Engineering graduation.",
        "guests": [
            ("Doto Mwakyusa", "Classmates", Guest.InvitationStatus.CHECKED_IN),
            ("Lilian Pauly", "Friends", Guest.InvitationStatus.CHECKED_IN),
            ("Godfrey Mtenga", "Colleagues", Guest.InvitationStatus.RSVP_YES),
            ("Sophia Iddi", "Family", Guest.InvitationStatus.RSVP_YES),
            ("Juma Rajabu", "Friends", Guest.InvitationStatus.RSVP_NO),
        ],
        "cards": [("Grad Modern", WhatsAppCard.Style.MODERN, "Class of 2026", False)],
        "pledges": [
            (200_000, 200_000, Pledge.Status.PAID, -30),
            (90_000, 90_000, Pledge.Status.PAID, -28),
            (60_000, 25_000, Pledge.Status.DEFAULTED, -1),
        ],
    },
]

TEMPLATES = [
    ("Invitation — SMS", MessageTemplate.Channel.SMS, None,
     "Habari {guest_name}! You are warmly invited to {event_title} on {event_date} at {venue}. "
     "RSVP: {rsvp_link}"),
    ("Invitation — WhatsApp", MessageTemplate.Channel.WHATSAPP, None,
     "Dear {guest_name}, you are cordially invited to *{event_title}*! "
     "{event_date} at {venue}. Kindly confirm your attendance here: {rsvp_link}"),
    ("Pledge Reminder", MessageTemplate.Channel.SMS, None,
     "Hello {guest_name}, a gentle reminder of your pledge of TZS {amount} for {event_title}. "
     "You can settle via mobile money. Asante!"),
]

LOG_MESSAGES = [
    (Guest.InvitationStatus.SENT, MessageLog.Status.SENT),
    (Guest.InvitationStatus.DELIVERED, MessageLog.Status.DELIVERED),
    (Guest.InvitationStatus.VIEWED, MessageLog.Status.DELIVERED),
]


class Command(BaseCommand):
    help = "Seed realistic demo data (users, events, guests, pledges, payments, messaging)."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Delete existing demo data first.")

    def handle(self, *args, **options):
        random.seed(2026)

        if options["flush"]:
            self._flush()

        created = {"users": 0, "events": 0, "guests": 0, "pledges": 0,
                   "payments": 0, "templates": 0, "cards": 0, "logs": 0}

        # ---- Users -----------------------------------------------------
        users = {}
        for spec in USERS:
            user, was_created = User.objects.get_or_create(
                email=spec["email"],
                defaults={
                    "name": spec["name"], "role": spec["role"], "status": spec["status"],
                    "phone": spec["phone"],
                    "is_approved": spec["status"] == User.Status.APPROVED,
                },
            )
            if was_created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
                created["users"] += 1
            users[spec["email"]] = user

        # ---- Events / guests / finance ---------------------------------
        pay_seq = Payment.objects.filter(reference__startswith="DEMO-").count() + 1
        for spec in EVENTS:
            event_date = date.today() + timedelta(days=spec["days"])
            slug = f"demo-{spec['title'].lower().replace(' ', '-').replace('—', '').replace('--', '-')}"
            event, was_created = Event.objects.get_or_create(
                slug=slug,
                defaults={
                    "user": users[spec["owner"]], "title": spec["title"],
                    "event_type": spec["event_type"], "status": spec["status"],
                    "description": spec["description"], "event_date": event_date,
                    "start_time": spec["start_time"], "end_time": spec["end_time"],
                    "venue": spec["venue"], "address": spec["address"],
                },
            )
            if not was_created:
                continue
            created["events"] += 1

            guests = []
            for name, category, inv_status in spec["guests"]:
                guest = Guest.objects.create(
                    event=event, name=name, category=category,
                    invitation_status=inv_status,
                    phone=f"07{random.randint(10, 99)}{random.randint(100000, 999999)}",
                    email=f"{name.split()[0].lower()}@example.com",
                )
                guests.append(guest)
                created["guests"] += 1

            for amount, paid, status, due_days in spec["pledges"]:
                pledge = Pledge.objects.create(
                    event=event, guest=random.choice(guests),
                    amount=amount, paid_amount=paid, status=status,
                    due_date=date.today() + timedelta(days=due_days),
                )
                created["pledges"] += 1
                if paid > 0:
                    payment = Payment.objects.create(
                        event=event, pledge=pledge, guest=pledge.guest,
                        provider="manual", reference=f"DEMO-{pay_seq:05d}",
                        amount=paid, status=(
                            Payment.Status.SUCCESS if paid >= amount else Payment.Status.SUCCESS
                        ),
                        paid_at=timezone.now() - timedelta(days=random.randint(1, 20)),
                    )
                    pay_seq += 1
                    created["payments"] += 1

            for name, style, headline, is_default in spec["cards"]:
                WhatsAppCard.objects.create(
                    event=event, name=name, style=style, headline=headline,
                    message="Karibu! We look forward to celebrating with you.",
                    is_default=is_default,
                )
                created["cards"] += 1

            # A few sent/delivered message logs
            for guest in guests[:3]:
                channel = random.choice([MessageTemplate.Channel.SMS, MessageTemplate.Channel.WHATSAPP])
                log_status = dict(LOG_MESSAGES).get(guest.invitation_status, MessageLog.Status.SENT)
                MessageLog.objects.create(
                    event=event, guest=guest, user=event.user, channel=channel,
                    recipient=guest.phone or guest.email,
                    message=f"Invitation to {event.title}", status=log_status,
                    sent_at=timezone.now() - timedelta(days=random.randint(1, 6)),
                )
                created["logs"] += 1

        # ---- Message templates ------------------------------------------
        for name, channel, subject, body in TEMPLATES:
            _, was_created = MessageTemplate.objects.get_or_create(
                name=name,
                defaults={"channel": channel, "subject": subject, "body": body, "is_system": True},
            )
            if was_created:
                created["templates"] += 1

        admin = User.objects.filter(is_superuser=True).first()
        AuditLog.objects.create(user=admin, action="demo_seeded", entity="system")

        self.stdout.write(self.style.SUCCESS(f"Demo data seeded: {created}"))
        self.stdout.write(f"Demo organizers login with password: {DEMO_PASSWORD}")
        self.stdout.write("  amina@demo.nialike.test / joseph@demo.nialike.test")
        self.stdout.write("  pending: grace@demo.nialike.test | suspended: daniel@demo.nialike.test")

    def _flush(self):
        deleted = []
        deleted.append(Payment.objects.filter(reference__startswith="DEMO-").delete()[0])
        deleted.append(Pledge.objects.filter(event__slug__startswith="demo-").delete()[0])
        deleted.append(MessageLog.objects.filter(event__slug__startswith="demo-").delete()[0])
        deleted.append(Guest.objects.filter(event__slug__startswith="demo-").delete()[0])
        deleted.append(WhatsAppCard.objects.filter(event__slug__startswith="demo-").delete()[0])
        deleted.append(Event.objects.filter(slug__startswith="demo-").delete()[0])
        deleted.append(MessageTemplate.objects.filter(name__in=[t[0] for t in TEMPLATES]).delete()[0])
        deleted.append(User.objects.filter(email__endswith="@demo.nialike.test").delete()[0])
        self.stdout.write(self.style.WARNING(f"Flushed previous demo data ({sum(deleted)} rows)."))
