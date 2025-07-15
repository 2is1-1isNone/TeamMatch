from django.db.models import Q
from .models import Team, DivisionSchedulingState, Club, Association


def user_navigation_context(request):
    """
    Context processor to provide navigation data based on user's team memberships and roles
    """
    if not request.user.is_authenticated:
        return {}
    
    user = request.user
    
    # Get teams based on user's roles
    user_teams = set()
    
    # 1. Teams where user is a member
    user_teams.update(user.teams.all())
    
    # 2. Teams where user is a team admin
    user_teams.update(user.admin_teams.all())
    
    # 3. Teams in clubs where user is a club director
    club_teams = Team.objects.filter(club__in=user.admin_clubs.all())
    user_teams.update(club_teams)
    
    # 4. Teams in associations where user is an association director
    association_teams = Team.objects.filter(club__association__in=user.admin_associations.all())
    user_teams.update(association_teams)
    
    # Convert to list and sort by name
    user_teams = sorted(list(user_teams), key=lambda t: t.name)
    
    # Get unique divisions from user's teams
    user_divisions = []
    if user_teams:
        # Get unique combinations of age_group, tier, season, association
        division_combinations = set()
        for team in user_teams:
            division_combinations.add((
                team.age_group,
                team.tier,
                team.season,
                team.club.association.id,
                team.club.association.name
            ))
        
        # Sort divisions by association name, then age group, then tier
        user_divisions = sorted(list(division_combinations), key=lambda d: (d[4], d[0], d[1]))
    
    # Get unique clubs from user's teams
    user_clubs = []
    if user_teams:
        club_set = set()
        for team in user_teams:
            club_set.add(team.club)
        user_clubs = sorted(list(club_set), key=lambda c: c.name)
    
    # Get unique associations from user's clubs
    user_associations = []
    if user_clubs:
        association_set = set()
        for club in user_clubs:
            association_set.add(club.association)
        user_associations = sorted(list(association_set), key=lambda a: a.name)
    
    return {
        'nav_teams': user_teams,
        'nav_divisions': user_divisions,
        'nav_clubs': user_clubs,
        'nav_associations': user_associations,
    }
