from django.core.management.base import BaseCommand
from users.services.dynamic_schedule_manager import DynamicScheduleManager
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Schedule deadline tasks for all pending league states'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--show-info',
            action='store_true',
            help='Show information about currently scheduled tasks',
        )
    
    def handle(self, *args, **options):
        if options['show_info']:
            self.show_scheduled_tasks()
        else:
            self.schedule_pending_deadlines()
    
    def schedule_pending_deadlines(self):
        """Schedule deadline tasks for all leagues with future deadlines"""
        self.stdout.write("Scheduling deadline tasks for pending leagues...")
        
        try:
            count = DynamicScheduleManager.schedule_all_pending_deadlines()
            self.stdout.write(
                self.style.SUCCESS(f'Successfully scheduled {count} deadline tasks')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error scheduling deadline tasks: {e}')
            )
    
    def show_scheduled_tasks(self):
        """Show information about currently scheduled tasks"""
        self.stdout.write("Currently scheduled deadline tasks:")
        
        try:
            tasks_info = DynamicScheduleManager.get_scheduled_tasks_info()
            
            if not tasks_info:
                self.stdout.write(self.style.WARNING("No scheduled tasks found"))
                return
            
            for info in tasks_info:
                self.stdout.write(
                    f"League: {info['league']}\n"
                    f"  Task ID: {info['task_id']}\n"
                    f"  Deadline: {info['deadline']}\n"
                    f"  Status: {info['status']}\n"
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error retrieving task info: {e}')
            )
