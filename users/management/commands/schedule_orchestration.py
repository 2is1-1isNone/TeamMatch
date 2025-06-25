from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import LeagueSchedulingState, Association, Team
from users.services.scheduling_orchestration_service import (
    SchedulingOrchestrationService, 
    run_daily_scheduling_checks
)

class Command(BaseCommand):
    help = 'Manage the scheduling orchestration system'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # Daily checks command
        daily_parser = subparsers.add_parser('daily', help='Run daily scheduling checks')
        
        # Manual trigger command
        trigger_parser = subparsers.add_parser('trigger', help='Manually trigger scheduling for a league')
        trigger_parser.add_argument('association_name', help='Association name')
        trigger_parser.add_argument('age_group', help='Age group (e.g., 16U)')
        trigger_parser.add_argument('tier', help='Tier (e.g., AAA)')
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Show status of all leagues')
        status_parser.add_argument('--association', help='Filter by association name')
        
        # Setup command
        setup_parser = subparsers.add_parser('setup', help='Setup scheduling state for a league')
        setup_parser.add_argument('association_name', help='Association name')
        setup_parser.add_argument('age_group', help='Age group (e.g., 16U)')
        setup_parser.add_argument('tier', help='Tier (e.g., AAA)')
        setup_parser.add_argument('--deadline-days', type=int, default=30, 
                                help='Days from now for availability deadline (default: 30)')

    def handle(self, *args, **options):
        action = options.get('action')
        
        if action == 'daily':
            self.handle_daily_checks()
        elif action == 'trigger':
            self.handle_manual_trigger(options)
        elif action == 'status':
            self.handle_status(options)
        elif action == 'setup':
            self.handle_setup(options)
        else:
            self.stdout.write(
                self.style.ERROR('Please specify an action: daily, trigger, status, or setup')
            )

    def handle_daily_checks(self):
        """Run the daily scheduling checks"""
        self.stdout.write("Running daily scheduling checks...")
        
        try:
            run_daily_scheduling_checks()
            self.stdout.write(
                self.style.SUCCESS('Daily scheduling checks completed successfully')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during daily checks: {e}')
            )

    def handle_manual_trigger(self, options):
        """Manually trigger scheduling for a specific league"""
        association_name = options['association_name']
        age_group = options['age_group']
        tier = options['tier']
        
        try:
            association = Association.objects.get(name=association_name)
        except Association.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Association "{association_name}" not found')
            )
            return
        
        self.stdout.write(f"Triggering scheduling for {association_name} {age_group} {tier}...")
        
        try:
            service = SchedulingOrchestrationService(age_group, tier, association)
            success, message = service.check_and_trigger_scheduling(manual_trigger=True)
            
            if success:
                self.stdout.write(
                    self.style.SUCCESS(f'Scheduling triggered successfully: {message}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Scheduling not triggered: {message}')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error triggering scheduling: {e}')
            )

    def handle_status(self, options):
        """Show status of all leagues"""
        association_filter = options.get('association')
        
        states = LeagueSchedulingState.objects.all().select_related('association')
        
        if association_filter:
            states = states.filter(association__name__icontains=association_filter)
        
        if not states.exists():
            self.stdout.write("No league scheduling states found.")
            return
        
        self.stdout.write("\nLeague Scheduling Status:")
        self.stdout.write("=" * 80)
        
        for state in states:
            teams = Team.objects.filter(
                age_group=state.age_group,
                tier=state.tier,
                association=state.association
            )
            
            self.stdout.write(f"\n{state.association.name} - {state.age_group} {state.tier}")
            self.stdout.write(f"  Status: {state.get_status_display()}")
            self.stdout.write(f"  Teams: {teams.count()}")
            self.stdout.write(f"  Deadline: {state.availability_deadline}")
            self.stdout.write(f"  Auto-schedule: {'Yes' if state.auto_schedule_enabled else 'No'}")
            
            if state.unmatched_teams.exists():
                self.stdout.write(f"  Unmatched teams: {', '.join([t.name for t in state.unmatched_teams.all()])}")
            
            if state.schedule_generated_at:
                from django.utils import timezone
                generated_pacific = timezone.localtime(state.schedule_generated_at)
                self.stdout.write(f"  Last scheduled: {generated_pacific} (Pacific)")

    def handle_setup(self, options):
        """Setup scheduling state for a league"""
        association_name = options['association_name']
        age_group = options['age_group']
        tier = options['tier']
        deadline_days = options['deadline_days']
        
        try:
            association = Association.objects.get(name=association_name)
        except Association.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Association "{association_name}" not found')
            )
            return
        
        # Check if teams exist for this league
        teams = Team.objects.filter(
            age_group=age_group,
            tier=tier,
            association=association
        )
        
        if not teams.exists():
            self.stdout.write(
                self.style.WARNING(f'No teams found for {association_name} {age_group} {tier}')
            )
            return
        
        deadline = timezone.now() + timezone.timedelta(days=deadline_days)
        
        state, created = LeagueSchedulingState.objects.get_or_create(
            age_group=age_group,
            tier=tier,
            association=association,
            defaults={
                'availability_deadline': deadline,
                'auto_schedule_enabled': True,
                'status': 'waiting'
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created scheduling state for {association_name} {age_group} {tier}\n'
                    f'  Teams: {teams.count()}\n'
                    f'  Deadline: {deadline}\n'
                    f'  Required series per team: {teams.count() - 1} home, {teams.count() - 1} away'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Scheduling state already exists for {association_name} {age_group} {tier}')
            )
