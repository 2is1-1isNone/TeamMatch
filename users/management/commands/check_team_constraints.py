from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Check database constraints on Team model'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Check for constraints on the users_team table
            cursor.execute("""
                SELECT conname, contype 
                FROM pg_constraint 
                WHERE conrelid = (
                    SELECT oid 
                    FROM pg_class 
                    WHERE relname = 'users_team'
                )
            """)
            constraints = cursor.fetchall()
            
            self.stdout.write("Constraints on users_team table:")
            for constraint_name, constraint_type in constraints:
                self.stdout.write(f"  {constraint_name}: {constraint_type}")
                
            # Also check indexes
            cursor.execute("""
                SELECT indexname, indexdef 
                FROM pg_indexes 
                WHERE tablename = 'users_team'
            """)
            indexes = cursor.fetchall()
            
            self.stdout.write("\nIndexes on users_team table:")
            for index_name, index_def in indexes:
                self.stdout.write(f"  {index_name}: {index_def}")
