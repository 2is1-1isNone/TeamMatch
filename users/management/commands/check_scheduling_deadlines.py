from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import LeagueSchedulingState
from users.services.schedule_orchestration import SchedulingOrchestrationService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check for leagues that have reached their scheduling deadline and trigger scheduling'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f'Checking scheduling deadlines at {timezone.now()}'))
        
        # Find all leagues that should trigger scheduling
        current_time = timezone.now()
        leagues_to_schedule = LeagueSchedulingState.objects.filter(
            auto_schedule_enabled=True,
            status='waiting',
            availability_deadline__lte=current_time
        )
        
        scheduled_count = 0
        for league_state in leagues_to_schedule:
            try:
                self.stdout.write(f'Processing {league_state}...')
                  # Create orchestration service
                service = SchedulingOrchestrationService(
                    league_state.age_group, 
                    league_state.tier, 
                    league_state.season,
                    league_state.association
                )
                
                # Attempt to trigger scheduling
                success, message = service.check_and_trigger_scheduling(manual_trigger=False)
                
                if success:
                    scheduled_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ {league_state}: {message}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'⚠ {league_state}: {message}')
                    )
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error processing {league_state}: {e}')
                )
                logger.error(f'Error in deadline scheduling for {league_state}: {e}')
        
        if scheduled_count == 0:
            self.stdout.write('No leagues required scheduling at this time.')
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully processed {scheduled_count} leagues')
            )
