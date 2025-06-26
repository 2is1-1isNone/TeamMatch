from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import DivisionSchedulingState
from users.services.schedule_orchestration import SchedulingOrchestrationService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check for divisions that have reached their scheduling deadline and trigger scheduling'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f'Checking scheduling deadlines at {timezone.now()}'))
        
        # Find all divisions that should trigger scheduling
        current_time = timezone.now()
        divisions_to_schedule = DivisionSchedulingState.objects.filter(
            auto_schedule_enabled=True,
            status='waiting',
            availability_deadline__lte=current_time
        )
        
        scheduled_count = 0
        for division_state in divisions_to_schedule:
            try:
                self.stdout.write(f'Processing {division_state}...')
                  # Create orchestration service
                service = SchedulingOrchestrationService(
                    division_state.age_group, 
                    division_state.tier, 
                    division_state.season,
                    division_state.association
                )
                
                # Attempt to trigger scheduling
                success, message = service.check_and_trigger_scheduling(manual_trigger=False)
                
                if success:
                    scheduled_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ {division_state}: {message}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'⚠ {division_state}: {message}')
                    )
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error processing {division_state}: {e}')
                )
                logger.error(f'Error in deadline scheduling for {division_state}: {e}')
        
        if scheduled_count == 0:
            self.stdout.write('No divisions required scheduling at this time.')
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully processed {scheduled_count} divisions')
            )
