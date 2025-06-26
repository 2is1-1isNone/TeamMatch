import threading
import time
from django.utils import timezone
from django.apps import AppConfig
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class ScheduleDeadlineChecker:
    """Simple background thread to check scheduling deadlines"""
    
    def __init__(self):
        self.should_stop = threading.Event()
        self.thread = None
    
    def start(self):
        """Start the background thread"""
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            logger.info("Schedule deadline checker started")
    
    def stop(self):
        """Stop the background thread"""
        self.should_stop.set()
        if self.thread:
            self.thread.join()
        logger.info("Schedule deadline checker stopped")
    
    def _run(self):
        """Main loop for checking deadlines"""
        while not self.should_stop.is_set():
            try:
                self._check_deadlines()
            except Exception as e:
                logger.error(f"Error in deadline checker: {e}")
            
            # Wait 5 minutes before next check (or until stop signal)
            self.should_stop.wait(300)  # 5 minutes = 300 seconds
    
    def _check_deadlines(self):
        """Check for divisions that need scheduling"""
        # Import here to avoid circular imports
        from users.models import DivisionSchedulingState
        from users.services.schedule_orchestration import SchedulingOrchestrationService
        
        current_time = timezone.now()
        divisions_to_schedule = DivisionSchedulingState.objects.filter(
            auto_schedule_enabled=True,
            status='waiting',
            availability_deadline__lte=current_time
        )
        
        for division_state in divisions_to_schedule:
            try:
                logger.info(f"Checking deadline for {division_state}")
                
                service = SchedulingOrchestrationService(
                    division_state.age_group, 
                    division_state.tier, 
                    division_state.association
                )
                
                success, message = service.check_and_trigger_scheduling(manual_trigger=False)
                
                if success:
                    logger.info(f"Scheduled {division_state}: {message}")
                else:
                    logger.warning(f"Could not schedule {division_state}: {message}")
                    
            except Exception as e:
                logger.error(f"Error processing {division_state}: {e}")

# Global instance
deadline_checker = ScheduleDeadlineChecker()
