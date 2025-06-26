from django.contrib import admin
from .models import (
    User, Association, Club, Team, TeamDate, TeamInvite, 
    Schedule, ScheduleProposal, DivisionSchedulingState, SchedulingNotification
)

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'title', 'is_active']
    search_fields = ['email', 'first_name', 'last_name']
    list_filter = ['is_active', 'is_staff']

@admin.register(Association)
class AssociationAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    filter_horizontal = ['admins']

@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ['name', 'association', 'created_at']
    search_fields = ['name', 'association__name']
    list_filter = ['association']
    filter_horizontal = ['admins']

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'club', 'age_group', 'tier', 'season', 'ready_for_scheduling']
    search_fields = ['name', 'club__name']
    list_filter = ['age_group', 'tier', 'season', 'ready_for_scheduling', 'club__association']
    filter_horizontal = ['members', 'admins']

@admin.register(TeamDate)
class TeamDateAdmin(admin.ModelAdmin):
    list_display = ['team', 'date', 'is_home', 'allow_doubleheader']
    search_fields = ['team__name']
    list_filter = ['is_home', 'allow_doubleheader', 'date', 'team__age_group', 'team__tier']

@admin.register(DivisionSchedulingState)
class DivisionSchedulingStateAdmin(admin.ModelAdmin):
    list_display = [
        'association', 'age_group', 'tier', 'status', 
        'availability_deadline', 'schedule_generated_at', 'auto_schedule_enabled'
    ]
    search_fields = ['association__name']
    list_filter = [
        'status', 'age_group', 'tier', 'auto_schedule_enabled', 
        'association', 'availability_deadline'
    ]
    readonly_fields = ['created_at', 'updated_at', 'last_schedule_attempt', 'schedule_generated_at']
    filter_horizontal = ['unmatched_teams']
    
    fieldsets = (
        ('Division Info', {
            'fields': ('association', 'age_group', 'tier')
        }),
        ('Scheduling Configuration', {
            'fields': ('availability_deadline', 'auto_schedule_enabled')
        }),
        ('Current State', {
            'fields': ('status', 'unmatched_teams')
        }),
        ('Timestamps', {
            'fields': ('last_schedule_attempt', 'schedule_generated_at', 'last_notification_sent'),
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(SchedulingNotification)
class SchedulingNotificationAdmin(admin.ModelAdmin):
    list_display = [
        'team', 'division_state', 'notification_type', 
        'sent_at', 'acknowledged'
    ]
    search_fields = ['team__name', 'division_state__association__name']
    list_filter = [
        'notification_type', 'acknowledged', 'sent_at',
        'division_state__age_group', 'division_state__tier'
    ]
    readonly_fields = ['sent_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'team', 'division_state', 'division_state__association'
        )

# Register other models without custom admin classes
admin.site.register(TeamInvite)
admin.site.register(Schedule)
admin.site.register(ScheduleProposal)
