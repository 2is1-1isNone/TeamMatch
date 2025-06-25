from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

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
    allow_doubleheader = models.BooleanField(default=False)  # <-- Add this line

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

class LeagueSchedulingState(models.Model):
    """Tracks the scheduling state for each league (age_group + tier + season combination)"""
    
    SCHEDULING_STATUS_CHOICES = [
        ('waiting', 'Waiting for Deadline/Conditions'),        ('triggered', 'Scheduling Triggered'),
        ('conflicts', 'Has Unresolved Conflicts'),
        ('completed', 'Schedule Complete'),
        ('manual_hold', 'Manual Hold')
    ]
    
    age_group = models.CharField(max_length=5, choices=Team.AGE_GROUPS)
    tier = models.CharField(max_length=3, choices=Team.TIERS)
    season = models.CharField(max_length=9, default="2024-2025")  # e.g., "2024-2025"
    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name='league_states')
    
    # Scheduling configuration
    availability_deadline = models.DateTimeField()
    auto_schedule_enabled = models.BooleanField(default=True)
    task_scheduled = models.BooleanField(default=False, help_text="Whether a deadline task is scheduled")
    last_schedule_attempt = models.DateTimeField(null=True, blank=True)
    
    # Current state
    status = models.CharField(max_length=20, choices=SCHEDULING_STATUS_CHOICES, default='waiting')
    schedule_generated_at = models.DateTimeField(null=True, blank=True)
    
    # Conflict tracking
    unmatched_teams = models.ManyToManyField(Team, blank=True, related_name='league_conflicts')
    last_notification_sent = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['age_group', 'tier', 'season', 'association']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.association.name} - {self.age_group} {self.tier} ({self.season}) - {self.status}"
    
    def should_trigger_scheduling(self):
        """Determine if scheduling should be triggered based on conditions"""
        # Manual hold overrides everything
        if self.status == 'manual_hold':
            return False, "Manual hold active"
        
        # Check if deadline reached
        deadline_reached = timezone.now() >= self.availability_deadline
        
        # Check if all teams have minimum availability
        teams = Team.objects.filter(
            age_group=self.age_group, 
            tier=self.tier,
            season=self.season,
            club__association=self.association
        )
        
        if teams.count() < 2:
            return False, "Insufficient teams in league"
        
        required_series = teams.count() - 1
        all_teams_ready = True
        
        for team in teams:
            home_dates = [td.date for td in team.dates.filter(is_home=True)]
            away_dates = [td.date for td in team.dates.filter(is_home=False)]
            
            home_series = self._count_weekend_series(home_dates)
            away_series = self._count_weekend_series(away_dates)
            
            if home_series < required_series or away_series < required_series:
                all_teams_ready = False
                break
        
        # Trigger if deadline reached AND all teams ready
        if deadline_reached and all_teams_ready:
            return True, "Deadline reached and all teams have sufficient availability"
        elif deadline_reached and not all_teams_ready:
            return False, "Deadline reached but some teams lack sufficient availability"
        elif all_teams_ready:
            return False, "Teams ready but deadline not reached"
        else:
            return False, "Deadline not reached and teams not ready"
    
    def _count_weekend_series(self, dates):
        """Count weekend series from dates (matching the view logic)"""
        if len(dates) < 2:
            return 0
        
        sorted_dates = sorted(dates)
        series_count = 0
        i = 0
        
        while i < len(sorted_dates) - 1:
            if (sorted_dates[i + 1] - sorted_dates[i]).days == 1:
                series_count += 1
                i += 2  # Skip the next date since it's part of this series
            else:
                i += 1
        
        return series_count

class SchedulingNotification(models.Model):
    """Track notifications sent to teams about scheduling conflicts"""
    NOTIFICATION_TYPES = [
        ('deadline_reminder', 'Deadline Reminder'),
        ('insufficient_availability', 'Insufficient Availability'),
        ('schedule_conflict', 'Schedule Conflict'),
        ('schedule_complete', 'Schedule Complete')
    ]
    
    league_state = models.ForeignKey(LeagueSchedulingState, on_delete=models.CASCADE, related_name='notifications')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='scheduling_notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    acknowledged = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"{self.team.name} - {self.notification_type} - {self.sent_at}"

class GeneratedSchedule(models.Model):
    """Stores generated league schedules with matches and metadata"""
    
    # League identification
    age_group = models.CharField(max_length=5, choices=Team.AGE_GROUPS)
    tier = models.CharField(max_length=3, choices=Team.TIERS)
    season = models.CharField(max_length=9, default="2024-2025")
    association = models.ForeignKey(Association, on_delete=models.CASCADE, related_name='generated_schedules')
    
    # Schedule metadata
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generated_schedules', null=True, blank=True)
    is_active = models.BooleanField(default=True, help_text="Whether this is the current active schedule")
    
    class Meta:
        ordering = ['-generated_at']
        unique_together = ['age_group', 'tier', 'season', 'association', 'is_active']
    
    def __str__(self):
        from django.utils import timezone
        generator = "System" if (self.generated_by and self.generated_by.username == 'system') else str(self.generated_by) if self.generated_by else "Unknown"
        # Convert UTC timestamp to Pacific Time for display
        generated_pacific = timezone.localtime(self.generated_at)
        return f"{self.association.name} - {self.age_group} {self.tier} ({self.season}) - Generated by {generator} at {generated_pacific} (Pacific)"

class ScheduleMatch(models.Model):
    """Individual matches within a generated schedule"""
    
    MATCH_TYPES = [
        ('series', 'Series'),
        ('single', 'Single Game'),
        ('doubleheader', 'Doubleheader'),
    ]
    
    MATCH_STATUS = [
        ('scheduled', 'Scheduled'),
        ('unscheduled', 'Unscheduled'),
        ('conflict', 'Conflict'),
    ]
    
    # Reference to the generated schedule
    generated_schedule = models.ForeignKey(GeneratedSchedule, on_delete=models.CASCADE, related_name='matches')
    
    # Match details
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_matches')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_matches')
    match_type = models.CharField(max_length=15, choices=MATCH_TYPES, default='series')
    status = models.CharField(max_length=15, choices=MATCH_STATUS, default='scheduled')
    
    # Match dates (stored as JSON for multiple dates)
    dates = models.JSONField(help_text="List of match dates in YYYY-MM-DD format")
    
    # Optional conflict reason for unscheduled matches
    conflict_reason = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['dates']
    
    def __str__(self):
        return f"{self.home_team.name} vs {self.away_team.name} - {self.dates}"

