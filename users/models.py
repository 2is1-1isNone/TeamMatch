from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    email = models.EmailField(unique=True, blank=False)
    title = models.CharField(max_length=100, blank=True, null=True, help_text="Optional user title, e.g., President")

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.title})" if self.title else f"{self.first_name} {self.last_name}"

class Association(models.Model):
    name = models.CharField(max_length=100)  # e.g., "PNAHA"
    created_at = models.DateTimeField(auto_now_add=True)
    admins = models.ManyToManyField('User', related_name='admin_associations', blank=True)

    def __str__(self):
        return self.name

class Club(models.Model):
    name = models.CharField(max_length=100)  # e.g., "Seattle Jr. Kraken"
    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name='clubs')
    created_at = models.DateTimeField(auto_now_add=True)
    admins = models.ManyToManyField('User', related_name='admin_clubs', blank=True)

    def __str__(self):
        return self.name

class Team(models.Model):
    AGE_GROUPS = [
        ('6U', '6U'), ('7U', '7U'), ('8U', '8U'), ('10U', '10U'), ('12U', '12U'),
        ('14U', '14U'), ('16U', '16U'), ('18U', '18U'), ('Adult', 'Adult'),
    ]
    TIERS = [
        ('A', 'A'), ('AA', 'AA'), ('AAA', 'AAA'), ('B', 'B'), ('BB', 'BB'), ('C', 'C'),
    ]

    name = models.CharField(max_length=100)  # e.g., "Seattle Jr. Kraken 18u C"
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='teams')
    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name='teams', null=True, blank=True)
    age_group = models.CharField(max_length=5, choices=AGE_GROUPS)
    tier = models.CharField(max_length=3, choices=TIERS)
    season = models.CharField(max_length=9)  # e.g., "2024-2025"
    description = models.TextField(blank=True, help_text="A brief description of the team.")
    location = models.CharField(max_length=100, blank=True, help_text="Team's home location (e.g., city or rink).")
    ready_for_scheduling = models.BooleanField(default=False)
    members = models.ManyToManyField(User, related_name='teams')
    admins = models.ManyToManyField('User', related_name='admin_teams', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Schedule(models.Model):
    EVENT_TYPES = [
        ('GAME', 'Game'),
        ('PRACTICE', 'Practice'),
    ]

    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_schedules', null=True, blank=True)
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_schedules', null=True, blank=True)
    event_type = models.CharField(max_length=10, choices=EVENT_TYPES)
    title = models.CharField(max_length=200)
    rink_location = models.CharField(max_length=100)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    season = models.CharField(max_length=9, blank=True, null=True)  # e.g., "2024-2025"
    is_series = models.BooleanField(default=False)  # For B, A, AA, AAA levels
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.event_type == 'GAME' and self.away_team:
            return f"{self.title} ({self.home_team.name} vs {self.away_team.name})"
        return f"{self.title} ({self.home_team.name})"

class TeamInvite(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    email = models.EmailField()
    accepted = models.BooleanField(default=False)
    invited_at = models.DateTimeField(auto_now_add=True)

class TeamDate(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='dates')
    date = models.DateField()
    is_home = models.BooleanField(default=True)

    class Meta:
        ordering = ['date']
        unique_together = ['team', 'date']  # Prevent duplicate dates for same team

class ScheduleProposal(models.Model):
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_proposals')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_proposals')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']

