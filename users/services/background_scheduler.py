"""
Simple background thread scheduler to replace Celery for deadline-based scheduling
"""
import threading
import time
import logging
import os
from datetime import datetime
from django.utils import timezone
from django.apps import apps

logger = logging.getLogger(__name__)

class BackgroundScheduler:
    """Simple background thread scheduler for division deadline scheduling"""
    
    def __init__(self):
        self.thread = None
        self.running = False
        self.check_interval = self._get_check_interval()  # Get interval from system settings
        self.instance_id = id(self)  # Unique identifier for this instance
    
    def _get_check_interval(self):
        """Get the current check interval from system settings"""
        try:
            from users.models import SystemSettings
            settings = SystemSettings.get_settings()
            interval = settings.scheduler_check_interval_seconds
            logger.info(f"Background scheduler using interval: {interval} seconds ({settings.scheduler_check_interval} {settings.scheduler_interval_unit})")
            return interval
        except Exception as e:
            logger.warning(f"Failed to get scheduler interval from settings, using default: {e}")
            return 60  # Default to 60 seconds if settings can't be loaded
    
    def start(self):
        """Start the background scheduler thread"""
        print(f"📍 BackgroundScheduler.start() called for instance {self.instance_id}")
        
        # Extra protection against multiple instances
        if self.thread and self.thread.is_alive():
            logger.warning(f"Background scheduler instance {self.instance_id} is already running")
            print(f"📍 Thread already alive, returning early")
            return
        
        print(f"📍 Setting running = True")
        logger.info(f"🚀 Starting background scheduler instance {self.instance_id}")
        self.running = True
        
        print(f"📍 Creating thread...")
        try:
            self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
            print(f"📍 Thread created: {self.thread}")
        except Exception as e:
            print(f"❌ Error creating thread: {e}")
            import traceback
            traceback.print_exc()
            raise
            
        print(f"📍 Starting thread...")
        try:
            self.thread.start()
            print(f"📍 Thread started successfully")
            
            # Give the thread a moment to actually start
            time.sleep(0.1)
            
            if self.thread.is_alive():
                print(f"📍 Thread is alive and running")
            else:
                print(f"⚠️ Thread was started but is not alive")
                
        except Exception as e:
            print(f"❌ Error starting thread: {e}")
            import traceback
            traceback.print_exc()
            raise
            
        logger.info(f"✅ Background scheduler instance {self.instance_id} started successfully")
        print(f"📍 BackgroundScheduler.start() completed")
    
    def stop(self):
        """Stop the background scheduler thread"""
        logger.info(f"🛑 Stopping background scheduler instance {self.instance_id}")
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info(f"✅ Background scheduler instance {self.instance_id} stopped")
    
    def _run_scheduler(self):
        """Main scheduler loop that checks for deadlines"""
        print(f"📍 _run_scheduler thread starting for instance {self.instance_id}")
        logger.info(f"🤖 Background scheduler thread {self.instance_id} started - checking for deadline triggers every {self.check_interval} seconds")
        
        settings_check_counter = 0
        settings_check_interval = 10  # Check settings every 10 cycles
        
        while self.running:
            try:
                print(f"📍 _run_scheduler checking deadlines...")
                self._check_deadlines()
                print(f"📍 _run_scheduler finished checking deadlines")
                
                # Periodically check for settings updates
                settings_check_counter += 1
                if settings_check_counter >= settings_check_interval:
                    self.update_check_interval()
                    settings_check_counter = 0
                    
            except Exception as e:
                print(f"❌ Error in _run_scheduler: {e}")  
                logger.error(f"❌ Error in background scheduler {self.instance_id}: {e}")
            
            # Sleep for the check interval
            logger.debug(f"😴 Background scheduler {self.instance_id} sleeping for {self.check_interval} seconds...")
            print(f"📍 _run_scheduler sleeping for {self.check_interval} seconds...")
            time.sleep(self.check_interval)
        
        print(f"📍 _run_scheduler thread ending for instance {self.instance_id}")
    
    def _check_deadlines(self):
        """Check all division states for deadline triggers"""
        print(f"📍 _check_deadlines called")
        
        # Get current time in Pacific timezone for logging
        current_time = timezone.now()
        pacific_time = timezone.localtime(current_time)
        logger.info(f"🔍 Background scheduler checking for divisions with passed deadlines at {pacific_time} (Pacific)")
        
        try:
            # Import here to avoid circular imports and ensure apps are loaded
            DivisionSchedulingState = apps.get_model('users', 'DivisionSchedulingState')
            print(f"📍 Got DivisionSchedulingState model")
            
            # Get all division states that might need scheduling
            all_division_states = DivisionSchedulingState.objects.all()
            logger.info(f"📊 Total division states in database: {all_division_states.count()}")
            
            eligible_states = DivisionSchedulingState.objects.filter(
                auto_schedule_enabled=True,
                status='waiting'
            )
            logger.info(f"📋 Division states with auto-schedule enabled and waiting status: {eligible_states.count()}")
            
            division_states = DivisionSchedulingState.objects.filter(
                auto_schedule_enabled=True,
                status='waiting',
                availability_deadline__lte=timezone.now()
            )
            
            if division_states.exists():
                logger.info(f"⏰ Found {division_states.count()} division(s) with passed deadlines - processing...")
                for division_state in division_states:
                    deadline_pacific = timezone.localtime(division_state.availability_deadline)
                    logger.info(f"  🎯 Processing: {division_state}")
                    logger.info(f"     Deadline: {deadline_pacific} (Pacific)")
                    logger.info(f"     Status: {division_state.status}")
                    logger.info(f"     Auto enabled: {division_state.auto_schedule_enabled}")
            else:
                logger.info(f"✅ No divisions found with passed deadlines requiring scheduling")
            
            for division_state in division_states:
                try:
                    logger.info(f"🔧 Checking trigger conditions for {division_state}")
                    should_trigger, reason = division_state.should_trigger_scheduling()
                    logger.info(f"   Should trigger: {should_trigger}, Reason: {reason}")
                    
                    if should_trigger:
                        logger.info(f"🎯 DEADLINE HIT! Triggering scheduling for {division_state}")
                        self._trigger_scheduling(division_state)
                    else:
                        logger.info(f"⚠️ Not triggering scheduling for {division_state}: {reason}")
                        
                except Exception as e:
                    logger.error(f"❌ Error checking deadline for {division_state}: {e}")
                    
        except Exception as e:
            print(f"❌ Error in _check_deadlines: {e}")
            logger.error(f"❌ Error in _check_deadlines: {e}")
            import traceback
            traceback.print_exc()
    
    def _trigger_scheduling(self, division_state):
        """Trigger scheduling for a division"""
        try:
            logger.info(f"🔥 BACKGROUND SCHEDULER: Initiating schedule generation for {division_state}")
            
            # Import here to avoid circular imports
            from users.services.schedule_orchestration import SchedulingOrchestrationService
            
            # Create orchestration service and trigger scheduling
            service = SchedulingOrchestrationService(
                division_state.age_group, 
                division_state.tier, 
                division_state.season,
                division_state.association
            )
            
            # Attempt to trigger scheduling
            success, message = service.check_and_trigger_scheduling(manual_trigger=False)
            
            if success:
                logger.info(f"🎉 BACKGROUND SCHEDULER: Successfully triggered scheduling for {division_state}: {message}")
            else:
                logger.warning(f"⚠️ BACKGROUND SCHEDULER: Failed to trigger scheduling for {division_state}: {message}")
            
            # Update the division state
            division_state.last_schedule_attempt = timezone.now()
            if success:
                division_state.status = 'triggered'
            division_state.save()
            
        except Exception as e:
            logger.error(f"❌ BACKGROUND SCHEDULER: Error triggering scheduling for {division_state}: {e}")
    
    def schedule_deadline_check(self, division_state):
        """Schedule a deadline check for a specific division (for immediate use)"""
        # For the background thread approach, we just mark it as scheduled
        # The background thread will pick it up on the next check
        division_state.task_scheduled = True
        division_state.save()
        logger.info(f"Scheduled deadline check for {division_state}")
    
    def cancel_deadline_check(self, division_state):
        """Cancel a scheduled deadline check"""
        division_state.task_scheduled = False
        division_state.save()
        logger.info(f"Cancelled deadline check for {division_state}")
    
    def update_check_interval(self):
        """Update the check interval from system settings without restarting the scheduler"""
        new_interval = self._get_check_interval()
        if new_interval != self.check_interval:
            old_interval = self.check_interval
            self.check_interval = new_interval
            logger.info(f"Background scheduler interval updated from {old_interval} to {new_interval} seconds")
        return self.check_interval


# Global scheduler instance
_scheduler = None
_scheduler_lock = threading.Lock()  # Thread lock for scheduler access

def get_scheduler():
    """Get or create the global background scheduler instance"""
    global _scheduler
    print(f"📍 get_scheduler() called, thread: {threading.current_thread().name}")
    print(f"📍 Current scheduler: {_scheduler}")
    print(f"📍 Attempting to acquire lock...")
    
    with _scheduler_lock:
        print(f"📍 get_scheduler() lock acquired in thread: {threading.current_thread().name}")
        if _scheduler is None:
            print("📍 Creating new scheduler instance...")
            logger.info("🔧 Creating new background scheduler instance")
            try:
                _scheduler = BackgroundScheduler()
                print(f"📍 New scheduler created: {_scheduler}")
            except Exception as e:
                print(f"❌ Error creating scheduler: {e}")
                import traceback
                traceback.print_exc()
                raise
        else:
            print(f"📍 Returning existing scheduler: {_scheduler}")
        print(f"📍 get_scheduler() about to return: {_scheduler}")
        return _scheduler

def start_scheduler():
    """Start the global background scheduler"""
    global _scheduler
    print(f"📍 start_scheduler() called, thread: {threading.current_thread().name}")
    try:
        print("📍 Acquiring scheduler lock in start_scheduler()...")
        with _scheduler_lock:
            print(f"📍 Lock acquired in start_scheduler(), thread: {threading.current_thread().name}")
            
            # Direct access to _scheduler instead of calling get_scheduler() to avoid nested locking
            if _scheduler is None:
                print("📍 Creating scheduler directly in start_scheduler()...")
                logger.info("🔧 Creating new background scheduler instance")
                _scheduler = BackgroundScheduler()
                print(f"📍 New scheduler created: {_scheduler}")
            
            scheduler = _scheduler
            print(f"📍 Got scheduler instance: {scheduler}")
            
            if scheduler.thread and scheduler.thread.is_alive():
                logger.warning("🚫 Background scheduler is already running - skipping start")
                print("📍 Scheduler already running, returning...")
                return
                
            print("📍 About to call scheduler.start()...")
            logger.info("🎯 Starting global background scheduler...")
            scheduler.start()
            print("📍 scheduler.start() completed")
            
    except Exception as e:
        print(f"❌ Exception in start_scheduler(): {e}")
        import traceback
        traceback.print_exc()

def stop_scheduler():
    """Stop the global background scheduler"""
    global _scheduler
    with _scheduler_lock:
        if _scheduler:
            logger.info("🛑 Stopping global background scheduler...")
            _scheduler.stop()
            _scheduler = None
            logger.info("✅ Global background scheduler stopped and cleared")
