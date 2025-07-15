from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.views.decorators.http import require_http_methods  # Add this line
from django.utils import timezone  # Add timezone import
import json  # Add json import
from .models import User, Team, Club, Association, Schedule, TeamInvite, TeamDate, DivisionSchedulingState, ScheduleProposal
from .forms import (
    CustomUserCreationForm, TeamForm, ScheduleForm, 
    ClubForm, AssociationForm, SimpleRegistrationForm,
    UserEditForm  # Add this import
)
from django.core.mail import send_mail  # At the top if you want to send real emails
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.http import JsonResponse
import json
from datetime import datetime
from users.services.schedule_orchestration import SchedulingOrchestrationService
from users.services.schedule_service import DivisionScheduler
from django.utils.dateformat import format as date_format

def register(request):
    if request.method == 'POST':
        form = SimpleRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.backend = settings.AUTHENTICATION_BACKENDS[0]
            login(request, user)
            # Assign to teams if invited (case-insensitive email lookup)
            invites = TeamInvite.objects.filter(email__iexact=user.email, accepted=False)
            for invite in invites:
                invite.team.members.add(user)
                invite.accepted = True
                invite.save()
            return redirect('home')
    else:
        form = SimpleRegistrationForm()
    return render(request, 'users/register.html', {'form': form})

def home(request):
    if request.user.is_authenticated:
        return redirect('home')  # Redirect to user_home
    return render(request, 'users/landing.html')

@login_required
def user_home(request):
    teams = request.user.teams.all()
    age_groups = Team._meta.get_field('age_group').choices
    tiers = Team._meta.get_field('tier').choices
    
    # Get all divisions (age_group + tier + season combinations) for associations the user manages
    divisions = []
    if request.user.admin_associations.exists():
        # Get unique combinations of age_group, tier, season for each association the user manages
        for association in request.user.admin_associations.all():
            division_combinations = Team.objects.filter(club__association=association).values(
                'age_group', 'tier', 'season'
            ).distinct().order_by('age_group', 'tier', 'season')
            
            for combo in division_combinations:
                divisions.append({
                    'association': association,
                    'age_group': combo['age_group'],
                    'tier': combo['tier'],
                    'season': combo['season']
                })
      # Get clubs the user administers
    admin_clubs = request.user.admin_clubs.all()
    
    return render(request, 'users/home.html', {
        'user': request.user,
        'teams': teams,
        'age_groups': age_groups,
        'tiers': tiers,
        'divisions': divisions,
        'admin_clubs': admin_clubs,  # Add club admin context
    })

@login_required
def team_profile(request, team_id=None):
    team = None
    if team_id is not None:
        team = get_object_or_404(Team, id=team_id)
    associations = Association.objects.all()
    clubs = Club.objects.all()
    teams = Team.objects.all()
    age_groups = Team._meta.get_field('age_group').choices
    tiers = Team._meta.get_field('tier').choices
    if request.method == 'POST':
        # Get association: either existing or new
        association_id = request.POST.get('association')
        new_association_name = request.POST.get('new_association_name')
        if new_association_name:
            association, created = Association.objects.get_or_create(name=new_association_name)
            if created:
                association.admins.add(request.user)  # Make creator admin
        elif association_id:
            association = Association.objects.get(id=association_id)
        else:
            association = None

        # Get club: either existing or new (similar logic if you want)
        club_id = request.POST.get('club')
        new_club_name = request.POST.get('new_club_name')
        if new_club_name and association:
            club, created = Club.objects.get_or_create(name=new_club_name, association=association)
            if created:
                club.add_admin(request.user)  # Make creator admin and member
        elif club_id:
            club = Club.objects.get(id=club_id)
        else:
            club = None

        # Team: either select existing or create new
        team_id = request.POST.get('team')
        if team_id:
            team = Team.objects.get(id=team_id)
        else:
            team_name = request.POST.get('team_name')
            age_group = request.POST.get('age_group')
            tier = request.POST.get('tier')
            season = request.POST.get('season')
            description = request.POST.get('description')
            location = request.POST.get('location')
            ready_for_scheduling = bool(request.POST.get('ready_for_scheduling'))

            team = Team.objects.create(
                name=team_name,
                club=club,
                age_group=age_group,
                tier=tier,
                season=season,
                description=description,
                location=location,
                ready_for_scheduling=ready_for_scheduling,
            )
            team.members.add(request.user)
            team.admins.add(request.user)        # New code for handling invites
        if not team_id:
            invite_emails = request.POST.get('invite_emails', '')
            for email in [e.strip().lower() for e in invite_emails.split(',') if e.strip()]:
                # Create a TeamInvite object (store email in lowercase)
                TeamInvite.objects.create(team=team, email=email)
                # Optionally send an email invite here

        return redirect('home')

    return render(request, 'users/team_profile.html', {
        'team': team,
        'associations': associations,
        'clubs': clubs,
        'teams': teams,
        'age_groups': age_groups,
        'tiers': tiers,
        # ...other context...
    })

@login_required
def create_schedule(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    # Ensure the user is a member of the team
    if request.user not in team.members.all():
        messages.error(request, "You do not have permission to create a schedule for this team.")
        return redirect('home')
    
    if request.method == 'POST':
        form = ScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.team = team
            schedule.save()
            messages.success(request, 'Schedule created successfully!')
            return redirect('home')
    else:
        form = ScheduleForm()
    return render(request, 'users/create_schedule.html', {'form': form, 'team': team})

from django.shortcuts import render, get_object_or_404
from .models import Team


@login_required
def delete_team(request, team_id):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('home')
    
    team = get_object_or_404(Team, id=team_id)
    team.delete()
    messages.success(request, f"Team {team.name} deleted successfully.")
    
    # Get return tab from query params
    return_tab = request.GET.get('return_tab', 'users')
    return redirect(f'/control_plane/#{return_tab}')

@login_required
def all_teams(request):
    age_group = request.GET.get('age_group')
    tier = request.GET.get('tier')
    club_id = request.GET.get('club_id')
    
    teams = Team.objects.all()
    if age_group:
        teams = teams.filter(age_group=age_group)
    if tier:
        teams = teams.filter(tier=tier)
    if club_id:
        teams = teams.filter(club_id=club_id)
        
    # Get club name for display if filtering by club
    club_name = None
    if club_id:
        try:
            club = Club.objects.get(id=club_id)
            club_name = club.name
        except Club.DoesNotExist:
            pass
            
    age_groups = Team._meta.get_field('age_group').choices
    tiers = Team._meta.get_field('tier').choices
    
    return render(request, 'users/all_teams.html', {
        'teams': teams,
        'age_groups': age_groups,
        'tiers': tiers,
        'selected_age_group': age_group,
        'selected_tier': tier,
        'club_name': club_name,  # Add club context for display
    })

@login_required
def users_list(request):
    from .models import User
    users = User.objects.all()
    return render(request, 'users/users_list.html', {'users': users})

@login_required
def billing(request):
    return render(request, 'users/billing.html')

@login_required
def team_calendar(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    
    # Get the division scheduling state for this team's division
    try:
        division_state = DivisionSchedulingState.objects.get(
            age_group=team.age_group,
            tier=team.tier,
            season=team.season,
            association=team.club.association
        )
        availability_deadline = division_state.availability_deadline
        # Convert to Pacific Time for display
        availability_deadline_local = timezone.localtime(availability_deadline) if availability_deadline else None
    except DivisionSchedulingState.DoesNotExist:
        availability_deadline_local = None
    
    # Get existing dates
    team_dates = TeamDate.objects.filter(team=team)
    team_dates_json = [
        {
            'title': 'Home Game' if date.is_home else 'Away Game',
            'start': date.date.strftime('%Y-%m-%d'),
            'allDay': True,
            'color': '#0d6efd' if date.is_home else '#ffb366',
            'allow_doubleheader': date.allow_doubleheader
        } for date in team_dates
    ]
      # Calculate division requirements and availability
    division_teams = Team.objects.filter(age_group=team.age_group, tier=team.tier)
    total_teams = division_teams.count()
    required_series = total_teams - 1  # Each team needs (N-1) home and (N-1) away series
      # Helper function to count weekend series from dates
    def count_weekend_series(dates):
        """Count actual weekend series (pairs of consecutive dates like Saturday-Sunday)"""
        if len(dates) < 2:
            return 0
        
        sorted_dates = sorted(dates)
        series_count = 0
        i = 0
        
        while i < len(sorted_dates) - 1:
            # Check if current date and next date are consecutive (1 day apart)
            if (sorted_dates[i + 1] - sorted_dates[i]).days == 1:
                series_count += 1
                i += 2  # Skip the next date since it's part of this series
            else:
                i += 1  # Move to next date
        
        return series_count    # Get home and away dates
    home_dates = [td.date for td in team_dates if td.is_home]
    away_dates = [td.date for td in team_dates if not td.is_home]
    
    # Count available weekend series
    available_home_series = count_weekend_series(home_dates)
    available_away_series = count_weekend_series(away_dates)
    
    # Calculate shortfalls - only show notifications if needed
    home_series_needed = max(0, required_series - available_home_series)
    away_series_needed = max(0, required_series - available_away_series)
      # Generate availability notifications
    availability_notifications = []
    if home_series_needed > 0:
        availability_notifications.append(f"Your team needs {home_series_needed} more home game weekend availability dates")
    if away_series_needed > 0:
        availability_notifications.append(f"Your team needs {away_series_needed} more away game weekend availability dates")
    
    context = {
        'team': team,
        'team_dates_json': json.dumps(team_dates_json),
        'required_series': required_series,
        'available_home_series': available_home_series,
        'available_away_series': available_away_series,
        'home_series_needed': home_series_needed,
        'away_series_needed': away_series_needed,
        'total_teams': total_teams,
        'availability_notifications': availability_notifications,
        'availability_deadline': availability_deadline_local
    }
    return render(request, 'users/team_calendar.html', context)

@login_required
@require_http_methods(["POST"])
def save_team_dates(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    data = json.loads(request.body)
    date_str = data.get('date')
    is_home = data.get('is_home')
    allow_doubleheader = data.get('allow_doubleheader', False)
     
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        if is_home is None:
            # Delete the date
            TeamDate.objects.filter(team=team, date=date_obj).delete()
        else:
            # Create or update the date, including allow_doubleheader
            obj, created = TeamDate.objects.update_or_create(
                team=team,
                date=date_obj,
                defaults={'is_home': is_home, 'allow_doubleheader': allow_doubleheader}
            )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def edit_team(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    if not (request.user.is_superuser or request.user in team.admins.all()):
        messages.error(request, "You do not have permission to edit this team.")
        return redirect('team_profile', team_id=team.id)
    if request.method == 'POST':
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, "Team updated successfully.")
            
            # Check if we came from control plane
            return_tab = request.GET.get('return_tab')
            if return_tab == 'teams':
                return redirect('control_plane' + '?return_tab=teams')
            else:
                return redirect('team_profile', team_id=team.id)
    else:
        form = TeamForm(instance=team)
    return render(request, 'users/edit_team.html', {'form': form, 'team': team})

@login_required
def invite_member(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    if request.user not in team.admins.all():
        messages.error(request, "You do not have permission to invite members.")
        return redirect('team_profile', team_id=team.id)
    if request.method == 'POST':
        email = request.POST.get('email')
        if email:
            # Store email in lowercase for case-insensitive handling
            email = email.strip().lower()
            # Create a TeamInvite object
            TeamInvite.objects.create(team=team, email=email)
            messages.success(request, f"Invitation sent to {email}.")
            # Optionally: send_mail(subject, message, from_email, [email])
    return redirect('team_profile', team_id=team.id)

@login_required
def create_club(request):
    if request.method == 'POST':
        form = ClubForm(request.POST)
        if form.is_valid():
            club = form.save()
            club.add_admin(request.user)  # Make creator admin and member
            messages.success(request, f"Club '{club.name}' created successfully.")
            return redirect('control_plane')
    else:
        form = ClubForm()
    return render(request, 'users/create_club.html', {'form': form})

@login_required
def create_association(request):
    if request.method == 'POST':
        form = AssociationForm(request.POST)
        if form.is_valid():
            association = form.save()
            association.admins.add(request.user)  # Make creator admin
            messages.success(request, f"Association '{association.name}' created successfully.")
            return redirect('control_plane')
    else:
        form = AssociationForm()
    return render(request, 'users/create_association.html', {'form': form})

@staff_member_required  # Only superusers/staff can access
def control_plane(request):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('home')

    users = User.objects.all().prefetch_related(
        'admin_teams',
        'admin_clubs',
        'admin_associations'
    )

    teams = Team.objects.all().select_related('club')
    clubs = Club.objects.all().select_related('association')
    associations = Association.objects.all()
    
    # Get system settings
    from users.models import SystemSettings
    system_settings = SystemSettings.get_settings()

    users_data = [{
        'user': user,
        'team_admin': user.admin_teams.all(),
        'club_admin': user.admin_clubs.all(),
        'association_admin': user.admin_associations.all(),
    } for user in users]

    return render(request, 'users/control_plane.html', {
        'users_data': users_data,
        'teams': teams,
        'clubs': clubs,
        'associations': associations,
        'system_settings': system_settings,
    })

@staff_member_required
@csrf_exempt
def make_team_admin(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        team_id = request.POST.get('team_id')
        user = User.objects.get(id=user_id)
        team = Team.objects.get(id=team_id)
        team.admins.add(user)
        messages.success(request, f"{user} is now a team admin for {team.name}.")
    return redirect('control_plane')

@staff_member_required
@csrf_exempt
def make_club_admin(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        club_id = request.POST.get('club_id')
        user = User.objects.get(id=user_id)
        club = Club.objects.get(id=club_id)
        club.add_admin(user)  # Make admin and member
        messages.success(request, f"{user} is now a club admin for {club.name}.")
    return redirect('control_plane')

@staff_member_required
@csrf_exempt
def make_association_admin(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        association_id = request.POST.get('association_id')
        user = User.objects.get(id=user_id)
        association = Association.objects.get(id=association_id)
        association.admins.add(user)
        messages.success(request, f"{user} is now an association admin for {association.name}.")
    return redirect('control_plane')

@staff_member_required
def edit_user(request, user_id):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('home')
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()  # This will now properly save all relationships
            messages.success(request, f"User {user.email} updated successfully.")
            return redirect('control_plane')
    else:
        form = UserEditForm(instance=user)
    
    return render(request, 'users/edit_user.html', {
        'form': form,
        'edit_user': user
    })

@staff_member_required
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        user.delete()
        messages.success(request, "User deleted.")
        return redirect('control_plane')
    return render(request, 'users/delete_user_confirm.html', {'user': user})

@login_required
def team_page(request, team_id):
    """Display the team page with calendar functionality"""
    team = get_object_or_404(Team, id=team_id)
    
    # Get the division scheduling state for this team's division
    try:
        division_state = DivisionSchedulingState.objects.get(
            age_group=team.age_group,
            tier=team.tier,
            season=team.season,
            association=team.club.association
        )
        availability_deadline = division_state.availability_deadline
        # Convert to Pacific Time for display
        availability_deadline_local = timezone.localtime(availability_deadline) if availability_deadline else None
    except DivisionSchedulingState.DoesNotExist:
        availability_deadline_local = None
    
    # Get existing dates
    team_dates = TeamDate.objects.filter(team=team)
    team_dates_json = [
        {
            'title': 'Home Game' if date.is_home else 'Away Game',
            'start': date.date.strftime('%Y-%m-%d'),
            'allDay': True,
            'color': '#0d6efd' if date.is_home else '#ffb366',
            'allow_doubleheader': date.allow_doubleheader
        } for date in team_dates
    ]
    
    # Calculate division requirements and availability
    division_teams = Team.objects.filter(age_group=team.age_group, tier=team.tier)
    total_teams = division_teams.count()
    required_series = total_teams - 1  # Each team needs (N-1) home and (N-1) away series
    
    # Helper function to count weekend series from dates
    def count_weekend_series(dates):
        """Count actual weekend series (pairs of consecutive dates like Saturday-Sunday)"""
        if len(dates) < 2:
            return 0
        
        sorted_dates = sorted(dates)
        series_count = 0
        i = 0
        
        while i < len(sorted_dates) - 1:
            # Check if current date and next date are consecutive (1 day apart)
            if (sorted_dates[i + 1] - sorted_dates[i]).days == 1:
                series_count += 1
                i += 2  # Skip the next date since it's part of this series
            else:
                i += 1  # Move to next date
        
        return series_count
    
    # Get home and away dates
    home_dates = [td.date for td in team_dates if td.is_home]
    away_dates = [td.date for td in team_dates if not td.is_home]
    
    # Count available weekend series
    available_home_series = count_weekend_series(home_dates)
    available_away_series = count_weekend_series(away_dates)
    
    # Calculate shortfalls - only show notifications if needed
    home_series_needed = max(0, required_series - available_home_series)
    away_series_needed = max(0, required_series - available_away_series)
    
    # Generate availability notifications
    availability_notifications = []
    if home_series_needed > 0:
        availability_notifications.append(f"Your team needs {home_series_needed} more home game weekend availability dates")
    if away_series_needed > 0:
        availability_notifications.append(f"Your team needs {away_series_needed} more away game weekend availability dates")
    
    context = {
        'team': team,
        'members': team.members.all(),
        'admins': team.admins.all(),
        'team_dates_json': json.dumps(team_dates_json),
        'required_series': required_series,
        'available_home_series': available_home_series,
        'available_away_series': available_away_series,
        'home_series_needed': home_series_needed,
        'away_series_needed': away_series_needed,
        'total_teams': total_teams,
        'availability_notifications': availability_notifications,
        'availability_deadline': availability_deadline_local
    }
    return render(request, 'users/team_page.html', context)

@login_required
def edit_club(request, club_id):
    """Edit club details"""
    club = get_object_or_404(Club, id=club_id)
    
    # Check if user has permission (superuser or club admin)
    if not (request.user.is_superuser or request.user in club.admins.all()):
        messages.error(request, "You don't have permission to edit this club.")
        return redirect('home')
    
    if request.method == 'POST':
        form = ClubForm(request.POST, instance=club)
        if form.is_valid():
            form.save()
            messages.success(request, f'Club "{club.name}" updated successfully.')
            
            # Check if we came from control plane
            return_tab = request.GET.get('return_tab')
            if return_tab == 'clubs':
                return redirect('control_plane' + '?return_tab=clubs')
            else:
                return redirect('control_plane')
    else:
        form = ClubForm(instance=club)
    
    return render(request, 'users/edit_club.html', {
        'form': form,
        'club': club
    })

@login_required
def delete_club(request, club_id):
    """Delete a club and redirect to the control plane with the Clubs tab active"""
    club = get_object_or_404(Club, id=club_id)

    # Check if user has permission or is a superuser
    if not request.user.is_superuser and request.user not in club.admins.all():
        messages.error(request, "You don't have permission to delete this club.")
        return redirect('home')

    if request.method == 'POST':
        club_name = club.name
        club.delete()
        messages.success(request, f'Club "{club_name}" has been deleted.')
        return redirect('/control_plane/?return_tab=clubs')

    return render(request, 'users/delete_club.html', {'club': club})

@login_required
def edit_association(request, association_id):
    """Edit an association's details"""
    association = get_object_or_404(Association, id=association_id)
    
    # Check if user has permission (superuser or association admin)
    if not (request.user.is_superuser or request.user in association.admins.all()):
        messages.error(request, "You don't have permission to edit this association.")
        return redirect('home')
    
    if request.method == 'POST':
        form = AssociationForm(request.POST, instance=association)
        if form.is_valid():
            form.save()
            messages.success(request, f'Association "{association.name}" updated successfully.')
            
            # Check if we came from control plane
            return_tab = request.GET.get('return_tab')
            if return_tab == 'associations':
                return redirect('control_plane' + '?return_tab=associations')
            else:
                return redirect('home')
    else:
        form = AssociationForm(instance=association)
    
    return render(request, 'users/edit_association.html', {
        'form': form,
        'association': association
    })

@login_required
def delete_association(request, association_id):
    """Handle deletion of an association"""
    association = get_object_or_404(Association, id=association_id)
    
    # Check if user has permission
    if request.user not in association.admins.all():
        messages.error(request, "You don't have permission to delete this association.")
        return redirect('home')
    
    if request.method == 'POST':
        association_name = association.name
        association.delete()
        messages.success(request, f'Association "{association_name}" has been deleted.')
        return redirect('home')
    
    return render(request, 'users/delete_association.html', {'association': association})


@login_required
def generate_division_schedule(request, age_group, tier, season, association_id):
    # Get the association and validate access
    try:
        association = Association.objects.get(id=association_id)
    except Association.DoesNotExist:
        messages.error(request, "Association not found")
        return redirect('home')
    
    # Check if user is an association admin
    if request.user not in association.admins.all():
        messages.error(request, "You must be an association admin to access the division scheduler")
        return redirect('home')
    
    # Get or create the division scheduling state
    from users.models import DivisionSchedulingState
    from django.utils import timezone
    division_state, created = DivisionSchedulingState.objects.get_or_create(
        age_group=age_group,
        tier=tier,
        season=season,
        association=association,
        defaults={
            'availability_deadline': timezone.now() + timezone.timedelta(days=30),
            'auto_schedule_enabled': True
        }
    )      # Handle deadline updates
    if request.method == 'POST' and 'update_deadline' in request.POST:
        deadline_str = request.POST.get('availability_deadline')
        auto_schedule = request.POST.get('auto_schedule_enabled') == 'on'
        
        if deadline_str:
            try:
                from datetime import datetime
                
                # Parse the datetime and make it timezone-aware in Pacific time
                deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
                new_deadline = timezone.make_aware(deadline)
                
                division_state.availability_deadline = new_deadline
                division_state.auto_schedule_enabled = auto_schedule
                # Reset status to 'waiting' so the background scheduler will pick it up
                division_state.status = 'waiting'
                division_state.save()
                
                # Create orchestration service and reschedule deadline task
                orchestration_service = SchedulingOrchestrationService(age_group, tier, season, association)
                task_id = orchestration_service.reschedule_deadline_task()
                
                if task_id:
                    messages.success(request, f"Division scheduling settings updated and deadline task scheduled!")
                else:
                    messages.success(request, "Division scheduling settings updated!")
                    
            except ValueError:
                messages.error(request, "Invalid deadline format. Please use the date picker.")
            except Exception as e:
                messages.error(request, f"Error scheduling deadline task: {str(e)}")
        
        return redirect('division_schedule', age_group=age_group, tier=tier, season=season, association_id=association_id)
      # Get teams in this specific division (age_group + tier + season + association)
    teams = Team.objects.filter(
        age_group=age_group, 
        tier=tier, 
        season=season,
        club__association=association
    )
    
    if not teams.exists():
        messages.error(request, f"No teams found for {age_group} {tier} {season} division")
        return redirect('home')
    
    # Initialize scheduler but don't generate schedule automatically when page is loaded
    scheduler = DivisionScheduler(age_group, tier, season, association)
    
    # Only get existing schedule proposals, don't generate new ones automatically
    existing_proposals = ScheduleProposal.objects.filter(
        home_team__age_group=age_group,
        home_team__tier=tier,
        home_team__season=season,
        home_team__club__association=association    ).exists()
    
    # Load existing generated schedule if available
    from users.models import GeneratedSchedule, ScheduleMatch
    
    # Check for existing active schedule
    existing_schedule = GeneratedSchedule.objects.filter(
        age_group=age_group,
        tier=tier,
        season=season,
        association=association,
        is_active=True
    ).first()
    
    schedule = []
    unscheduled_matches = []
    
    if existing_schedule:
        print(f"=== LOADING EXISTING SCHEDULE FROM DB ===")
        # Convert UTC timestamp to Pacific Time for display
        generated_pacific = timezone.localtime(existing_schedule.generated_at)
        print(f"Schedule ID: {existing_schedule.id}, Generated: {generated_pacific} (Pacific)")
        
        # Load scheduled matches
        scheduled_matches = ScheduleMatch.objects.filter(
            generated_schedule=existing_schedule,
            status='scheduled'
        ).select_related('home_team', 'away_team')
        
        for match in scheduled_matches:
            # Convert date strings back to date objects for template compatibility
            dates_as_dates = []
            for date_str in match.dates:
                from datetime import datetime
                dates_as_dates.append(datetime.strptime(date_str, '%Y-%m-%d').date())
            
            schedule.append({
                'home_team': match.home_team,
                'away_team': match.away_team,
                'dates': dates_as_dates,
                'status': match.status,
                'type': match.match_type
            })
        
        # Load unscheduled matches
        unscheduled_match_records = ScheduleMatch.objects.filter(
            generated_schedule=existing_schedule,
            status='unscheduled'
        ).select_related('home_team', 'away_team')
        
        for match in unscheduled_match_records:
            unscheduled_matches.append({
                'home_team': match.home_team,
                'away_team': match.away_team,
                'reason': match.conflict_reason or 'Scheduling conflict'
            })
    
    # If no existing schedule, initialize empty data structures
    
    # New code to include teams' availability dates with doubleheader info and status
    teams_with_availability = []
    total_teams = teams.count()
    required_series = total_teams - 1  # Each team needs (N-1) home and (N-1) away series
    
    # Helper function to count weekend series from dates
    def count_weekend_series(dates):
        """Count actual weekend series (pairs of consecutive dates like Saturday-Sunday)"""
        if len(dates) < 2:
            return 0
        
        sorted_dates = sorted(dates)
        series_count = 0
        i = 0
        
        while i < len(sorted_dates) - 1:
            # Check if current date and next date are consecutive (1 day apart)
            if (sorted_dates[i + 1] - sorted_dates[i]).days == 1:
                series_count += 1
                i += 2  # Skip the next date since it's part of this series
            else:
                i += 1  # Move to next date
        
        return series_count
    
    for team in teams:
        # Get home dates with doubleheader info
        home_date_objects = TeamDate.objects.filter(team=team, is_home=True).values('date', 'allow_doubleheader')
        away_date_objects = TeamDate.objects.filter(team=team, is_home=False).values('date', 'allow_doubleheader')
        
        # Extract dates for counting weekend series
        home_dates = [obj['date'] for obj in home_date_objects]
        away_dates = [obj['date'] for obj in away_date_objects]
        
        # Calculate availability status using weekend series count
        available_home_series = count_weekend_series(home_dates)
        available_away_series = count_weekend_series(away_dates)
        
        home_series_needed = max(0, required_series - available_home_series)
        away_series_needed = max(0, required_series - available_away_series)
        
        teams_with_availability.append({
            'team': team,
            'home_dates': home_date_objects,
            'away_dates': away_date_objects,
            'home_series_needed': home_series_needed,
            'away_series_needed': away_series_needed,
            'available_home_series': available_home_series,
            'available_away_series': available_away_series,
            'required_series': required_series,
        })

    if unscheduled_matches:
        messages.warning(
            request, 
            f"Schedule generated with {len(unscheduled_matches)} conflicts that need resolution"
        )
    
    return render(request, 'users/division_schedule.html', {
        'schedule': schedule,
        'unscheduled_matches': unscheduled_matches,
        'age_group': age_group,
        'tier': tier,
        'season': season,
        'association': association,
        'teams_with_availability': teams_with_availability,
        'division_state': division_state,  # Add deadline management context
    })

@login_required
@require_http_methods(["POST"])
def generate_schedule_service(request, age_group, tier, season, association_id):
    from users.models import GeneratedSchedule, ScheduleMatch
    
    print("=" * 80)
    print("🚀 MANUAL SCHEDULE GENERATION TRIGGERED")
    print("=" * 80)
    print(f"📋 Age Group: {age_group}")
    print(f"📋 Tier: {tier}")
    print(f"📋 Season: {season}")
    print(f"📋 Association ID: {association_id}")
    print(f"👤 User: {request.user.username} (ID: {request.user.id})")
    print(f"⏰ Timestamp: {timezone.now()}")
    print(f"🔧 Request method: {request.method}")
    print("=" * 80)
    
    try:
        # Get the association and validate access
        try:
            association = Association.objects.get(id=association_id)
        except Association.DoesNotExist:
            raise Exception("Association not found")        # Check if user is an association admin
        if request.user not in association.admins.all():
            raise Exception("You must be an association admin to generate schedules")        # Delete any existing schedule and its matches - use a transaction for consistency
        from django.db import transaction
        
        with transaction.atomic():
            # Delete all existing schedules and their matches
            existing_schedules = GeneratedSchedule.objects.filter(
                age_group=age_group,
                tier=tier,
                season=season,
                association=association
            )
            
            print(f"=== FOUND {existing_schedules.count()} EXISTING SCHEDULES TO DELETE ===")
            for i, schedule in enumerate(existing_schedules, 1):
                match_count = ScheduleMatch.objects.filter(generated_schedule=schedule).count()
                print(f"  Deleting schedule {i} (ID: {schedule.id}) with {match_count} matches")
                ScheduleMatch.objects.filter(generated_schedule=schedule).delete()
            existing_schedules.delete()
            print("=== EXISTING SCHEDULES DELETED ===")
        print("=== CALLING DIVISION_SCHEDULER.CREATE_SCHEDULE ===")
        scheduler = DivisionScheduler(age_group, tier, season, association)
        schedule, unscheduled_matches = scheduler.create_schedule()
        print(f"Schedule returned: {len(schedule)} matches, {len(unscheduled_matches)} unscheduled")
        
        print("=== SAVING GENERATED SCHEDULE TO DATABASE ===")
        # Create new GeneratedSchedule record
        print("=== SAVING GENERATED SCHEDULE TO DATABASE ===")
        generated_schedule = GeneratedSchedule.objects.create(
            age_group=age_group,
            tier=tier,
            season=season,
            association=association,
            generated_by=request.user,
            is_active=True        )
        print(f"Generated schedule saved with ID: {generated_schedule.id}")
        
        print(f"=== SAVING {len(schedule)} SCHEDULED MATCHES TO DATABASE ===")
        # Save all matches to the database
        for i, match in enumerate(schedule, 1):
            # Convert dates to strings if they're date objects
            dates_list = []
            for date in match['dates']:
                if hasattr(date, 'strftime'):
                    dates_list.append(date.strftime('%Y-%m-%d'))
                else:
                    dates_list.append(str(date))
            
            ScheduleMatch.objects.create(
                generated_schedule=generated_schedule,
                home_team=match['home_team'],
                away_team=match['away_team'],
                dates=dates_list,
                match_type=match.get('type', 'series'),
                status='scheduled'            )
            print(f"  Match {i}: {match['home_team'].name} vs {match['away_team'].name} saved")
        
        print(f"=== SAVING {len(unscheduled_matches)} UNSCHEDULED MATCHES TO DATABASE ===")
        # Save unscheduled matches as well (for tracking conflicts)
        for i, match in enumerate(unscheduled_matches, 1):
            ScheduleMatch.objects.create(
                generated_schedule=generated_schedule,
                home_team=match['home_team'],
                away_team=match['away_team'],
                dates=[],  # No dates for unscheduled matches
                match_type='series',  # Default type
                status='unscheduled',  # Important: mark as unscheduled
                conflict_reason=match.get('reason', 'Scheduling conflict')
            )
            print(f"  Unscheduled Match {i}: {match['home_team'].name} vs {match['away_team'].name} - {match.get('reason', 'Scheduling conflict')}")

        # Get teams and their availability data for the template
        teams = Team.objects.filter(
            age_group=age_group, 
            tier=tier, 
            season=season,
            club__association=association
        )
        
        teams_with_availability = []
        for team in teams:
            home_date_objects = TeamDate.objects.filter(team=team, is_home=True).values('date', 'allow_doubleheader')
            away_date_objects = TeamDate.objects.filter(team=team, is_home=False).values('date', 'allow_doubleheader')
            teams_with_availability.append({
                'team': team,
                'home_dates': home_date_objects,
                'away_dates': away_date_objects
            })

        # Get or create division state for template context
        from users.models import DivisionSchedulingState
        division_state, created = DivisionSchedulingState.objects.get_or_create(
            age_group=age_group,
            tier=tier,
            season=season,
            association=association,
            defaults={
                'availability_deadline': timezone.now() + timezone.timedelta(days=30),
                'auto_schedule_enabled': True
            }
        )
        
        if unscheduled_matches:            messages.warning(
                request,
                f"Schedule generated with {len(unscheduled_matches)} unscheduled matches that need resolution"
            )
        else:
            messages.success(request, "Schedule generated successfully!")
        
        print("=== REDIRECTING TO DIVISION_SCHEDULE ===")
        # Redirect back to the division schedule page to load fresh data from database
        return redirect('division_schedule', 
                       age_group=age_group, 
                       tier=tier, 
                       season=season, 
                       association_id=association_id)                       
    except Exception as e:
        error_message = str(e)
        print(f"ERROR in generate_schedule_service: {error_message}")
        messages.error(request, f"Error generating schedule: {error_message}")
        return redirect('division_schedule', 
                       age_group=age_group, 
                       tier=tier, 
                       season=season, 
                       association_id=association_id)

@login_required
def division_calendar(request, age_group, tier, season, association_id):
    # Get the association
    try:
        association = Association.objects.get(id=association_id)
    except Association.DoesNotExist:
        messages.error(request, "Association not found")
        return redirect('home')
    
    # Get teams in this specific division
    teams = Team.objects.filter(
        age_group=age_group, 
        tier=tier, 
        season=season,
        club__association=association
    )
    if not teams.exists():
        messages.error(request, f"No teams found for {age_group} {tier} {season} division")
        return redirect('home')
    
    # Load existing generated schedule
    from users.models import GeneratedSchedule, ScheduleMatch
    
    existing_schedule = GeneratedSchedule.objects.filter(
        age_group=age_group,
        tier=tier,
        season=season,
        association=association,
        is_active=True
    ).first()
    
    schedule = []
    has_generated_calendar = False
    
    if existing_schedule:
        has_generated_calendar = True
        # Load scheduled matches from database
        scheduled_matches = ScheduleMatch.objects.filter(
            generated_schedule=existing_schedule,
            status='scheduled'
        ).select_related('home_team', 'away_team')
        
        for match in scheduled_matches:
            # Convert date strings back to date objects for template compatibility
            dates_as_dates = []
            for date_str in match.dates:
                from datetime import datetime
                dates_as_dates.append(datetime.strptime(date_str, '%Y-%m-%d').date())
            
            schedule.append({
                'home_team': match.home_team,
                'away_team': match.away_team,
                'dates': dates_as_dates,
                'status': match.status,
                'type': match.match_type
            })
    
    # Serialize schedule to JSON for FullCalendar
    events = []
    for match in schedule:
        # Simple title and color for all matches
        title = f"{match['home_team'].name} vs {match['away_team'].name}"
        color = '#0d6efd'  # Blue for all games
            
        # Handle the date format - matches have 'dates' array for series
        match_dates = match.get('dates', [])
        if not match_dates:
            continue  # Skip if no dates
            
        event = {
            'title': title,
            'start': date_format(match_dates[0], 'Y-m-d'),
            'allDay': True,
            'color': color,            'extendedProps': {
                'home': match['home_team'].name,
                'away': match['away_team'].name,
                'type': match['type']
            }
        }
        
        # Handle multi-day series
        if len(match_dates) > 1:
            # FullCalendar expects end to be exclusive, so add one day
            from datetime import timedelta
            end_date = match_dates[1] + timedelta(days=1)
            event['end'] = date_format(end_date, 'Y-m-d')
            
        events.append(event)
    
    events_json = json.dumps(events)
    return render(request, 'users/division_calendar.html', {
        'schedule': schedule,
        'association': association,
        'age_group': age_group,
        'tier': tier,
        'season': season,
        'events_json': events_json,
        'has_generated_calendar': has_generated_calendar,
        'division_name': f"{age_group} {tier}",
    })

@login_required
def clubs_list(request, association_id):
    """View clubs for a specific association - only accessible by association admins"""
    try:
        association = Association.objects.get(id=association_id)
    except Association.DoesNotExist:
        messages.error(request, "Association not found")
        return redirect('home')
    
    # Check if user is an association admin
    if request.user not in association.admins.all():
        messages.error(request, "You must be an association admin to view clubs")
        return redirect('home')
    
    # Get all clubs in this association
    clubs = Club.objects.filter(association=association).order_by('name')
    
    # Add team count for each club
    clubs_with_stats = []
    for club in clubs:
        team_count = club.teams.count()
        clubs_with_stats.append({
            'club': club,
            'team_count': team_count
        })
    
    return render(request, 'users/clubs_list.html', {
        'association': association,
        'clubs_with_stats': clubs_with_stats,
    })

@login_required
def association_divisions(request, association_id):
    """Show all divisions for an association admin"""
    from users.models import DivisionSchedulingState  # Import at function level
    
    try:
        association = Association.objects.get(id=association_id)
    except Association.DoesNotExist:
        messages.error(request, "Association not found")
        return redirect('home')
      # Check if user is an association admin
    if request.user not in association.admins.all():
        messages.error(request, "You must be an association admin to access this page")
        return redirect('home')
    
    # Handle division settings updates
    if request.method == 'POST':
        if 'update_division_settings' in request.POST:
            # Handle season settings update
            season_start = request.POST.get('season_start')
            season_end = request.POST.get('season_end')
            
            # Store season settings in request.session (you might want to add these fields to Association model later)
            current_settings = request.session.get('division_settings', {})
            current_settings.update({
                'season_start': season_start,
                'season_end': season_end,
            })
            request.session['division_settings'] = current_settings
            
            messages.success(request, "Season settings updated successfully!")
            return redirect('association_divisions', association_id=association_id)
            
        elif 'update_deadline_settings' in request.POST:
            # Handle deadline settings update
            scheduling_deadline = request.POST.get('scheduling_deadline')
            apply_to_all = request.POST.get('apply_deadline_to_all') == 'on'
            
            # Store deadline setting in request.session
            current_settings = request.session.get('division_settings', {})
            current_settings['scheduling_deadline'] = scheduling_deadline
            request.session['division_settings'] = current_settings
            
            if apply_to_all and scheduling_deadline:
                # Update all division scheduling states for this association
                from datetime import datetime
                try:
                    deadline = datetime.strptime(scheduling_deadline, '%Y-%m-%dT%H:%M')
                    deadline_aware = timezone.make_aware(deadline)
                    
                    updated_count = DivisionSchedulingState.objects.filter(
                        association=association
                    ).update(availability_deadline=deadline_aware)
                    
                    messages.success(request, f"Scheduling deadline updated for {updated_count} divisions!")
                except ValueError:
                    messages.error(request, "Invalid deadline format")
            else:
                messages.success(request, "Deadline settings updated successfully!")
            
            return redirect('association_divisions', association_id=association_id)
    
    # Get division settings from session or set defaults
    division_settings = request.session.get('division_settings', {
        'season_start': '',
        'season_end': '',
        'scheduling_deadline': (timezone.now() + timezone.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M')
    })
    
    # Get all unique division combinations for this association
    divisions = Team.objects.filter(club__association=association).values(
        'age_group', 'tier', 'season'
    ).distinct().order_by('season', 'age_group', 'tier')
    
    # Get team counts for each division and scheduling state
    divisions_with_data = []
    for division in divisions:
        teams_in_division = Team.objects.filter(
            club__association=association,
            age_group=division['age_group'],
            tier=division['tier'],
            season=division['season']        )
        
        # Get or create division scheduling state
        division_state, created = DivisionSchedulingState.objects.get_or_create(
            age_group=division['age_group'],
            tier=division['tier'],
            season=division['season'],
            association=association,
            defaults={
                'availability_deadline': timezone.now() + timezone.timedelta(days=30),
                'auto_schedule_enabled': True
            }
        )
        
        divisions_with_data.append({
            'age_group': division['age_group'],
            'tier': division['tier'],
            'season': division['season'],
            'team_count': teams_in_division.count(),
            'division_state': division_state,            'teams': list(teams_in_division.select_related('club').values(
                'id', 'name', 'description', 'location', 'club__name'
            )),
        })
    
    return render(request, 'users/association_divisions.html', {
        'association': association,
        'divisions': divisions_with_data,
        'divisions_json': json.dumps(divisions_with_data, default=str),
        'division_settings': division_settings,  # Add division settings to context
    })

@login_required
def user_profile(request):
    """Display user profile page"""
    return render(request, 'users/user_profile.html', {
        'user': request.user
    })

@login_required  
def edit_user_profile(request):
    """Edit user profile - email and password"""
    if request.method == 'POST':
        # Handle email change
        new_email = request.POST.get('email', '').strip()
        if new_email and new_email != request.user.email:
            # Check if email is already taken
            if User.objects.filter(email=new_email).exclude(id=request.user.id).exists():
                messages.error(request, 'This email address is already in use.')
            else:
                request.user.email = new_email
                request.user.save()
                messages.success(request, 'Email address updated successfully.')
        
        # Handle password change
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        if current_password and new_password and confirm_password:
            # Check current password
            if not request.user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != confirm_password:
                messages.error(request, 'New passwords do not match.')
            elif len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters long.')
            else:
                request.user.set_password(new_password)
                request.user.save()
                # Re-authenticate user after password change
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password updated successfully.')
        
        return redirect('user_profile')
    
    return render(request, 'users/edit_user_profile.html', {
        'user': request.user
    })

@login_required
@require_http_methods(["POST"])
def send_unscheduled_notifications(request, age_group, tier, season, association_id):
    """
    Send email notifications to teams with unscheduled matches
    """
    import json
    from django.http import JsonResponse
    from django.core.mail import send_mail
    from django.conf import settings
    from users.models import ScheduleMatch, GeneratedSchedule
    
    try:
        # Get the association and validate access
        try:
            association = Association.objects.get(id=association_id)
        except Association.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Association not found'})
        
        # Check if user is an association admin
        if request.user not in association.admins.all():
            return JsonResponse({'success': False, 'message': 'You must be an association admin to send notifications'})
        
        # Get the existing schedule
        existing_schedule = GeneratedSchedule.objects.filter(
            age_group=age_group,
            tier=tier,
            season=season,
            association=association,
            is_active=True
        ).first()
        
        if not existing_schedule:
            return JsonResponse({'success': False, 'message': 'No active schedule found'})
        
        # Get unscheduled matches
        unscheduled_matches = ScheduleMatch.objects.filter(
            generated_schedule=existing_schedule,
            status='unscheduled'
        ).select_related('home_team', 'away_team')
        
        if not unscheduled_matches.exists():
            return JsonResponse({'success': False, 'message': 'No unscheduled matches found'})
        
        # Collect all teams involved in unscheduled matches
        teams_involved = set()
        for match in unscheduled_matches:
            teams_involved.add(match.home_team)
            teams_involved.add(match.away_team)
        
        # Build the email content
        subject = f'[{association.name}] Unscheduled Matches Notification - {age_group} {tier} ({season})'
        
        # Create a detailed message with all unscheduled matches
        message_lines = [
            f'Hello Team Members,',
            f'',
            f'This is an automated notification regarding unscheduled matches in the {association.name} {age_group} {tier} division for the {season} season.',
            f'',
            f'Your team is involved in matches that could not be scheduled due to conflicts:',
            f'',
        ]
        
        for match in unscheduled_matches:
            message_lines.append(f'• {match.home_team.name} (Home) vs {match.away_team.name} (Away)')
            if match.conflict_reason:
                message_lines.append(f'  Status: {match.conflict_reason}')
            message_lines.append('')
        
        message_lines.extend([
            f'To resolve these scheduling conflicts:',
            f'1. Team managers/admins should review your team\'s availability dates',
            f'2. Add more weekend dates when your team can play',
            f'3. Contact the division administrator if you need assistance',
            f'',
            f'Once teams have updated their availability, the schedule will be regenerated automatically.',
            f'',
            f'If you have any questions, please contact your team manager or the division administrator.',
            f'',
            f'Best regards,',
            f'{association.name} Division Management System'
        ])
        
        message = '\n'.join(message_lines)
        
        # Send emails to team admins, managers, coaches, and all team members
        teams_notified = 0
        total_emails_sent = 0
        
        for team in teams_involved:
            # Get all recipients with email addresses
            recipients = []
            
            # Add team admins
            for admin in team.admins.all():
                if admin.email and admin.email not in recipients:
                    recipients.append(admin.email)
                    print(f"  📧 Added admin: {admin.email}")
            
            # Add team members
            for member in team.members.all():
                if member.email and member.email not in recipients:
                    recipients.append(member.email)
                    print(f"  📧 Added member: {member.email}")
            
            # Add managers if they exist (check if team has managers field)
            if hasattr(team, 'managers'):
                for manager in team.managers.all():
                    if manager.email and manager.email not in recipients:
                        recipients.append(manager.email)
                        print(f"  📧 Added manager: {manager.email}")
            
            # Add coaches if they exist (check if team has coaches field)  
            if hasattr(team, 'coaches'):
                for coach in team.coaches.all():
                    if coach.email and coach.email not in recipients:
                        recipients.append(coach.email)
                        print(f"  📧 Added coach: {coach.email}")
            
            print(f"🔍 Team {team.name}: Found {len(recipients)} email recipients")
            
            if recipients:
                try:
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipients,
                        fail_silently=False
                    )
                    teams_notified += 1
                    total_emails_sent += len(recipients)
                    print(f"✅ Email sent to {team.name}: {recipients}")
                except Exception as e:
                    print(f"❌ Failed to send email to {team.name}: {e}")
            else:
                print(f"⚠️ No email addresses found for team {team.name}")
        
        return JsonResponse({
            'success': True, 
            'message': f'Notifications sent to team members successfully',
            'teams_notified': teams_notified,
            'total_emails_sent': total_emails_sent
        })
        
    except Exception as e:
        print(f"❌ Error sending unscheduled match notifications: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
@require_http_methods(["POST"])
def send_availability_notifications(request, age_group, tier, season, association_id):
    """
    Send email notifications to teams that need more weekend availability
    """
    import json
    from django.http import JsonResponse
    from django.core.mail import send_mail
    from django.conf import settings
    
    try:
        # Get the association and validate access
        try:
            association = Association.objects.get(id=association_id)
        except Association.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Association not found'})
        
        # Check if user is an association admin
        if request.user not in association.admins.all():
            return JsonResponse({'success': False, 'message': 'You must be an association admin to send notifications'})
        
        # Get teams for this division
        teams = Team.objects.filter(
            club__association=association,
            age_group=age_group,
            tier=tier,
            season=season
        )
        
        if not teams.exists():
            return JsonResponse({'success': False, 'message': 'No teams found for this division'})
        
        # Calculate which teams need more availability
        total_teams = teams.count()
        required_series = total_teams - 1  # Each team needs (N-1) home and (N-1) away series
        
        # Helper function to count weekend series from dates
        def count_weekend_series(dates):
            """Count actual weekend series (pairs of consecutive dates like Saturday-Sunday)"""
            if len(dates) < 2:
                return 0
            
            sorted_dates = sorted(dates)
            series_count = 0
            i = 0
            
            while i < len(sorted_dates) - 1:
                # Check if current date and next date are consecutive (1 day apart)
                if (sorted_dates[i + 1] - sorted_dates[i]).days == 1:
                    series_count += 1
                    i += 2  # Skip the next date since it's part of this series
                else:
                    i += 1  # Move to next date
            
            return series_count
        
        # Find teams that need more availability
        teams_needing_availability = []
        
        for team in teams:
            # Get availability dates
            home_dates = list(TeamDate.objects.filter(team=team, is_home=True).values_list('date', flat=True))
            away_dates = list(TeamDate.objects.filter(team=team, is_home=False).values_list('date', flat=True))
            
            # Calculate availability status
            available_home_series = count_weekend_series(home_dates)
            available_away_series = count_weekend_series(away_dates)
            
            home_series_needed = max(0, required_series - available_home_series) 
            away_series_needed = max(0, required_series - available_away_series)
            
            # If team needs more home or away availability, add to notification list
            if home_series_needed > 0 or away_series_needed > 0:
                teams_needing_availability.append({
                    'team': team,
                    'home_series_needed': home_series_needed,
                    'away_series_needed': away_series_needed,
                    'available_home_series': available_home_series,
                    'available_away_series': available_away_series,
                    'required_series': required_series
                })
        
        if not teams_needing_availability:
            return JsonResponse({'success': False, 'message': 'All teams have sufficient availability. No notifications sent.'})
        
        # Send emails to teams needing more availability
        teams_notified = 0
        total_emails_sent = 0
        
        for team_data in teams_needing_availability:
            team = team_data['team']
            
            # Build personalized email content for this team
            subject = f'[{association.name}] Weekend Availability Required - {age_group} {tier} ({season})'
            
            message_lines = [
                f'Hello {team.name} Team Members,',
                f'',
                f'This is an automated notification regarding weekend availability for the {association.name} {age_group} {tier} division ({season} season).',
                f'',
                f'Your team currently needs to add more weekend availability dates:',
                f'',
            ]
            
            if team_data['home_series_needed'] > 0:
                message_lines.append(f'• Home Weekend Series: Need {team_data["home_series_needed"]} more ({team_data["available_home_series"]}/{team_data["required_series"]} available)')
            
            if team_data['away_series_needed'] > 0: 
                message_lines.append(f'• Away Weekend Series: Need {team_data["away_series_needed"]} more ({team_data["available_away_series"]}/{team_data["required_series"]} available)')
            
            message_lines.extend([
                f'',
                f'A weekend series consists of consecutive dates (e.g., Saturday-Sunday).',
                f'',
                f'To add more availability:',
                f'1. Log into the team scheduling system',
                f'2. Go to your team calendar',
                f'3. Add weekend dates when your team can play home/away games',
                f'4. Make sure to mark consecutive weekend dates (Saturday-Sunday pairs)',
                f'',
                f'Adding sufficient availability helps ensure all your matches can be scheduled.',
                f'',
                f'If you have any questions, please contact your team manager or the division administrator.',
                f'',
                f'Best regards,',
                f'{association.name} Division Management System'
            ])
            
            message = '\n'.join(message_lines)
            
            # Get all recipients with email addresses
            recipients = []
            
            # Add team admins
            for admin in team.admins.all():
                if admin.email and admin.email not in recipients:
                    recipients.append(admin.email)
            
            # Add team members
            for member in team.members.all():
                if member.email and member.email not in recipients:
                    recipients.append(member.email)
            
            # Add managers if they exist
            if hasattr(team, 'managers'):
                for manager in team.managers.all():
                    if manager.email and manager.email not in recipients:
                        recipients.append(manager.email)
            
            # Add coaches if they exist  
            if hasattr(team, 'coaches'):
                for coach in team.coaches.all():
                    if coach.email and coach.email not in recipients:
                        recipients.append(coach.email)
            
            print(f"🔍 Team {team.name}: Found {len(recipients)} email recipients (needs home: {team_data['home_series_needed']}, away: {team_data['away_series_needed']})")
            
            if recipients:
                try:
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipients,
                        fail_silently=False
                    )
                    teams_notified += 1
                    total_emails_sent += len(recipients)
                    print(f"✅ Availability notification sent to {team.name}: {recipients}")
                except Exception as e:
                    print(f"❌ Failed to send availability notification to {team.name}: {e}")
            else:
                print(f"⚠️ No email addresses found for team {team.name}")
        
        return JsonResponse({
            'success': True, 
            'message': f'Availability notifications sent successfully',
            'teams_notified': teams_notified,
            'total_emails_sent': total_emails_sent
        })
        
    except Exception as e:
        print(f"❌ Error sending availability notifications: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


@staff_member_required
def update_system_settings(request):
    """
    Update system settings like scheduler check interval
    """
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('home')
    
    try:
        from users.models import SystemSettings
        
        # Get or create system settings
        system_settings = SystemSettings.get_settings()
        
        # Update the settings
        system_settings.scheduler_check_interval = int(request.POST.get('scheduler_check_interval', 10))
        system_settings.scheduler_interval_unit = request.POST.get('scheduler_interval_unit', 'seconds')
        system_settings.updated_by = request.user
        system_settings.save()
        
        # Update the running background scheduler
        try:
            from users.apps import scheduler_instance
            if scheduler_instance:
                old_interval = scheduler_instance.check_interval
                new_interval = scheduler_instance.update_check_interval()
                messages.success(
                    request, 
                    f"System settings updated successfully! Scheduler interval changed from {old_interval} to {new_interval} seconds."
                )
            else:
                messages.success(request, "System settings updated successfully!")
        except Exception as e:
            messages.warning(
                request, 
                f"Settings updated but failed to notify running scheduler: {str(e)}. Changes will take effect on next restart."
            )
        
    except Exception as e:
        messages.error(request, f"Failed to update system settings: {str(e)}")
    
    return redirect('control_plane')

@login_required
def division_page(request, age_group, tier, season, association_id):
    """Display a division page with Teams, Calendar, and Logs options"""
    association = get_object_or_404(Association, id=association_id)
    
    # Get teams in this division
    teams = Team.objects.filter(
        age_group=age_group,
        tier=tier,
        season=season,
        club__association=association
    )
    
    context = {
        'age_group': age_group,
        'tier': tier,
        'season': season,
        'association': association,
        'teams': teams,
        'division_name': f"{age_group} {tier}",
    }
    return render(request, 'users/division_page.html', context)

@login_required
def division_teams(request, age_group, tier, season, association_id):
    """Display all teams in a specific division"""
    association = get_object_or_404(Association, id=association_id)
    
    # Get teams in this division
    teams = Team.objects.filter(
        age_group=age_group,
        tier=tier,
        season=season,
        club__association=association
    ).select_related('club').prefetch_related('admins', 'members')
    
    context = {
        'age_group': age_group,
        'tier': tier,
        'season': season,
        'association': association,
        'teams': teams,
        'division_name': f"{age_group} {tier}",
    }
    return render(request, 'users/division_teams.html', context)

@staff_member_required
def create_user(request):
    """Create a new user - only accessible by superusers"""
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('home')
    
    if request.method == 'POST':
        form = SimpleRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"User {user.email} created successfully.")
            return redirect('control_plane')
    else:
        form = SimpleRegistrationForm()
    
    return render(request, 'users/create_user.html', {'form': form})

@login_required
def create_team(request):
    """Create a new team with redesigned form flow"""
    associations = Association.objects.all()
    clubs = Club.objects.all()
    age_groups = Team._meta.get_field('age_group').choices
    tiers = Team._meta.get_field('tier').choices
    
    if request.method == 'POST':
        team_name = request.POST.get('team_name')
        age_group = request.POST.get('age_group')
        tier = request.POST.get('tier')
        season = request.POST.get('season')
        description = request.POST.get('description')
        location = request.POST.get('location')
        ready_for_scheduling = bool(request.POST.get('ready_for_scheduling'))
        
        # Handle club selection/creation
        club_choice = request.POST.get('club_choice')  # 'existing' or 'new'
        
        if club_choice == 'existing':
            club_id = request.POST.get('existing_club')
            if club_id:
                club = Club.objects.get(id=club_id)
            else:
                messages.error(request, 'Please select an existing club.')
                return render(request, 'users/create_team.html', {
                    'associations': associations,
                    'clubs': clubs,
                    'age_groups': age_groups,
                    'tiers': tiers,
                })
        else:  # new club
            new_club_name = request.POST.get('new_club_name')
            new_club_location = request.POST.get('new_club_location', '')
            association_choice = request.POST.get('association_choice')  # 'existing' or 'new'
            
            if not new_club_name:
                messages.error(request, 'Please enter a club name.')
                return render(request, 'users/create_team.html', {
                    'associations': associations,
                    'clubs': clubs,
                    'age_groups': age_groups,
                    'tiers': tiers,
                })
            
            if association_choice == 'existing':
                association_id = request.POST.get('existing_association')
                if association_id:
                    association = Association.objects.get(id=association_id)
                else:
                    messages.error(request, 'Please select an existing association.')
                    return render(request, 'users/create_team.html', {
                        'associations': associations,
                        'clubs': clubs,
                        'age_groups': age_groups,
                        'tiers': tiers,
                    })
            else:  # new association
                new_association_name = request.POST.get('new_association_name')
                if not new_association_name:
                    messages.error(request, 'Please enter an association name.')
                    return render(request, 'users/create_team.html', {
                        'associations': associations,
                        'clubs': clubs,
                        'age_groups': age_groups,
                        'tiers': tiers,
                    })
                
                # Create new association
                association, created = Association.objects.get_or_create(name=new_association_name)
                if created:
                    association.admins.add(request.user)
            
            # Create new club
            club, created = Club.objects.get_or_create(
                name=new_club_name, 
                association=association,
                defaults={'location': new_club_location}
            )
            if created:
                club.add_admin(request.user)  # Make creator admin and member
        
        # Create the team
        team = Team.objects.create(
            name=team_name,
            club=club,
            age_group=age_group,
            tier=tier,
            season=season,
            description=description,
            location=location,
            ready_for_scheduling=ready_for_scheduling,
        )
        team.members.add(request.user)
        team.admins.add(request.user)
        
        # Also add user to club members if not already
        club.members.add(request.user)
        
        # Handle invites
        invite_emails = request.POST.get('invite_emails', '')
        for email in [e.strip().lower() for e in invite_emails.split(',') if e.strip()]:
            TeamInvite.objects.create(team=team, email=email)
        
        messages.success(request, f'Team "{team_name}" created successfully!')
        return redirect('control_plane')
    
    return render(request, 'users/create_team.html', {
        'associations': associations,
        'clubs': clubs,
        'age_groups': age_groups,
        'tiers': tiers,
    })