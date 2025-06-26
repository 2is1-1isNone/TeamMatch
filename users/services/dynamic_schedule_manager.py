from django.utils import timezone
from users.models import DivisionSchedulingState
from users.services.background_scheduler import get_scheduler
import logging

logger = logging.getLogger(__name__)

class DynamicScheduleManager:
    """
    Manages dynamic scheduling for division availability deadlines using background threads
    """
    
    @staticmethod
    def schedule_division_deadline(division_state):
        """
        Schedule a background task to trigger at the division's availability deadline
        """
        try:
            # Cancel existing task if any
            DynamicScheduleManager.cancel_existing_task(division_state)
            
            # Don't schedule if deadline is in the past
            if division_state.availability_deadline <= timezone.now():
                logger.info(f"Deadline is in the past for {division_state}, not scheduling task")
                return None
                
            # Don't schedule if auto-scheduling is disabled
            if not division_state.auto_schedule_enabled:
                logger.info(f"Auto-scheduling disabled for {division_state}, not scheduling task")
                return None
            
            # Schedule with background scheduler
            scheduler = get_scheduler()
            scheduler.schedule_deadline_check(division_state)
            
            logger.info(f"Scheduled deadline check for {division_state} at {division_state.availability_deadline}")
            return f"bg_task_{division_state.id}"  # Return a simple task identifier
            
        except Exception as e:
            logger.error(f"Failed to schedule deadline task for {division_state}: {e}")
            return None
    
    @staticmethod
    def cancel_existing_task(division_state):
        """
        Cancel existing background task for this division state
        """
        if division_state.task_scheduled:
            try:
                scheduler = get_scheduler()
                scheduler.cancel_deadline_check(division_state)
                logger.info(f"Cancelled existing task for {division_state}")
                
            except Exception as e:
                logger.error(f"Failed to cancel task for {division_state}: {e}")
    
    @staticmethod
    def reschedule_division_deadline(division_state):
        """
        Reschedule a division deadline (cancel old task and create new one)
        """
        logger.info(f"Rescheduling deadline for {division_state}")
        return DynamicScheduleManager.schedule_division_deadline(division_state)
    
    @staticmethod
    def schedule_all_pending_deadlines():
        """
        Schedule tasks for all divisions that have future deadlines but no scheduled task
        """
        pending_states = DivisionSchedulingState.objects.filter(
            availability_deadline__gt=timezone.now(),
            auto_schedule_enabled=True,
            task_scheduled=False,
            status='waiting'
        )
        
        scheduled_count = 0
        for division_state in pending_states:
            task_id = DynamicScheduleManager.schedule_division_deadline(division_state)
            if task_id:
                scheduled_count += 1
        
        logger.info(f"Scheduled {scheduled_count} pending deadline tasks")
        return scheduled_count
    
    @staticmethod
    def get_scheduled_tasks_info():
        """
        Get information about all scheduled tasks
        """
        scheduled_states = DivisionSchedulingState.objects.filter(
            task_scheduled=True
        ).select_related('association')
        
        tasks_info = []
        for state in scheduled_states:
            tasks_info.append({
                'division': str(state),
                'task_scheduled': state.task_scheduled,
                'deadline': state.availability_deadline,
                'status': state.status
            })
        
        return tasks_info
