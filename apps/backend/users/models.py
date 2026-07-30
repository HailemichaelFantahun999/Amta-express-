from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The email address must be set.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, username=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", User.Status.ACTIVE)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        DISPATCHER = "dispatcher", "Dispatcher"
        DRIVER = "driver", "Driver"
        CUSTOMER = "customer", "Customer"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        AVAILABLE = "available", "Available"
        ON_TRIP = "on_trip", "On Trip"
        OFFLINE = "offline", "Offline"
        INACTIVE = "inactive", "Inactive"

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    avatar = models.CharField(max_length=4, blank=True)
    can_create_users = models.BooleanField(default=False)
    department = models.CharField(max_length=100, blank=True, default="")
    must_change_password = models.BooleanField(default=False)
    last_active_at = models.DateTimeField(null=True, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    blood_type = models.CharField(max_length=5, blank=True)
    driver_image = models.TextField(blank=True)
    fayda_id_number = models.CharField(max_length=100, blank=True)
    fayda_id_image = models.TextField(blank=True)
    home_location = models.CharField(max_length=255, blank=True, default="")
    work_location = models.CharField(max_length=255, blank=True, default="")
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5)
    performance_score = models.PositiveIntegerField(default=100)
    last_location_lat = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    last_location_lng = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save(self, *args, **kwargs):
        full_name = self.get_full_name().strip() or self.email
        initials = "".join(part[0].upper() for part in full_name.split()[:2] if part)
        if not self.avatar:
            self.avatar = initials[:2] or "DU"
        self.email = self.email.lower()
        self.username = self.email
        super().save(*args, **kwargs)

    def touch(self):
        self.last_active_at = timezone.now()
        self.save(update_fields=["last_active_at"])

    def __str__(self):
        return f"{self.get_full_name() or self.email} ({self.role})"

    def calculate_average_rating(self):
        from features.deliveries.models import DriverRating

        ratings = DriverRating.objects.filter(driver=self)
        if ratings.exists():
            avg_rating = ratings.aggregate(avg=models.Avg("rating"))["avg"]
            return round(avg_rating, 2)
        return 0.0

    def update_rating(self):
        self.rating = self.calculate_average_rating()
        self.save(update_fields=["rating"])
