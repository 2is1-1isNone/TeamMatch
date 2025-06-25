from django.apps import AppConfig
import os


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    
    def ready(self):
        """Start the background scheduler when Django is ready"""
        # Only start scheduler in the main process (not during auto-reload)
        # This prevents multiple scheduler instances during development
        if os.environ.get('RUN_MAIN', None) != 'true':
            return
            
        from users.services.background_scheduler import start_scheduler
        import threading
        
        # Only start scheduler in the main thread (not in reloader)
        if not threading.current_thread().daemon:
            print("🚀 Django app ready - starting background scheduler...")
            try:
                print("🔄 About to call start_scheduler()...")
                start_scheduler()
                print("✅ Background scheduler startup completed")
            except Exception as e:
                print(f"❌ Error starting background scheduler: {e}")
                import traceback
                traceback.print_exc()
