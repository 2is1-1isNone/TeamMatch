from django.core.management.base import BaseCommand
from users.models import Team

class Command(BaseCommand):
    help = 'Check for duplicate team names'

    def handle(self, *args, **options):
        # Check for the specific team
        teams = Team.objects.filter(name='Seattle Kraken 14U B')
        self.stdout.write(f'Found {teams.count()} teams with name "Seattle Kraken 14U B"')
        
        for team in teams:
            self.stdout.write(f'ID: {team.id}, Name: {team.name}, Club: {team.club}')
        
        # Check for any duplicate names
        from django.db.models import Count
        duplicates = Team.objects.values('name').annotate(name_count=Count('name')).filter(name_count__gt=1)
        
        if duplicates:
            self.stdout.write('\nFound duplicate team names:')
            for dup in duplicates:
                self.stdout.write(f'  {dup["name"]}: {dup["name_count"]} teams')
        else:
            self.stdout.write('\nNo duplicate team names found')
