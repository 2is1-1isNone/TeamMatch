from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.views.decorators.http import require_http_methods  # Add this line
from django.utils import timezone  # Add timezone import
import json  # Add json import
from .models import User, Team, Club, Association, Schedule, TeamInvite, TeamDate, LeagueSchedulingState, ScheduleProposal
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
from users.services.schedule_service import LeagueScheduler
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
            return redirect('dashboard')
    else:
        form = SimpleRegistrationForm()
    return render(request, 'users/register.html', {'form': form})

def home(request):
    return render(request, 'users/home.html')

@login_required
def dashboard(request):
    teams = request.user.teams.all()
    age_groups = Team._meta.get_field('age_group').choices
    tiers = Team._meta.get_field('tier').choices
    
    # Get all leagues (age_group + tier + season combinations) for associations the user manages
    leagues = []
    if request.user.admin_associations.exists():
        # Get unique combinations of age_group, tier, season for each association the user manages
        for association in request.user.admin_associations.all():
            league_combinations = Team.objects.filter(club__association=association).values(
                'age_group', 'tier', 'season'
            ).distinct().order_by('age_group', 'tier', 'season')
            
            for combo in league_combinations:
                leagues.append({
                    'association': association,
                    'age_group': combo['age_group'],
                    'tier': combo['tier'],
                    'season': combo['season']
                })
      # Get clubs the user administers
    admin_clubs = request.user.admin_clubs.all()
    
    return render(request, 'users/dashboard.html', {
        'user': request.user,
        'teams': teams,
        'age_groups': age_groups,
        'tiers': tiers,
        'leagues': leagues,
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
                club.admins.add(request.user)  # Make creator admin
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
                association=association,
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

        return redirect('dashboard')

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
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.team = team
            schedule.save()
            messages.success(request, 'Schedule created successfully!')
            return redirect('dashboard')
    else:
        form = ScheduleForm()
    return render(request, 'users/create_schedule.html', {'form': form, 'team': team})

from django.shortcuts import render, get_object_or_404
from .models import Team


@login_required
def delete_team(request, team_id):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('dashboard')
    
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
      # Calculate league requirements and availability
    league_teams = Team.objects.filter(age_group=team.age_group, tier=team.tier)
    total_teams = league_teams.count()
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
        'availability_notifications': availability_notifications
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
    if request.user not in team.admins.all():
        messages.error(request, "You do not have permission to edit this team.")
        return redirect('team_profile', team_id=team.id)
    if request.method == 'POST':
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, "Team updated successfully.")
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
            club.admins.add(request.user)  # Make creator admin
            return redirect('dashboard')
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
            return redirect('dashboard')
    else:
        form = AssociationForm()
    return render(request, 'users/create_association.html', {'form': form})

@staff_member_required  # Only superusers/staff can access
def control_plane(request):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('dashboard')

    users = User.objects.all().prefetch_related(
        'admin_teams',
        'admin_clubs',
        'admin_associations'
    )

    teams = Team.objects.all().select_related('club')
    clubs = Club.objects.all().select_related('association')
    associations = Association.objects.all()

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
        'associations': associations
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
        club.admins.add(user)
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
        return redirect('dashboard')
    
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
    """Display the public team page with basic info"""
    team = get_object_or_404(Team, id=team_id)
    context = {
        'team': team,
        'members': team.members.all(),
        'admins': team.admins.all()
    }
    return render(request, 'users/team_page.html', context)

@login_required
def edit_club(request, club_id):
    """Edit club details"""
    club = get_object_or_404(Club, id=club_id)
    
    # Check if user has permission
    if request.user not in club.admins.all():
        messages.error(request, "You don't have permission to edit this club.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ClubForm(request.POST, instance=club)
        if form.is_valid():
            form.save()
            messages.success(request, 'Club updated successfully.')
            return redirect('dashboard')
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
        return redirect('dashboard')

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
    
    # Check if user has permission
    if request.user not in association.admins.all():
        messages.error(request, "You don't have permission to edit this association.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AssociationForm(request.POST, instance=association)
        if form.is_valid():
            form.save()
            messages.success(request, 'Association updated successfully.')
            return redirect('dashboard')
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
        return redirect('dashboard')
    
    if request.method == 'POST':
        association_name = association.name
        association.delete()
        messages.success(request, f'Association "{association_name}" has been deleted.')
        return redirect('dashboard')
    
    return render(request, 'users/delete_association.html', {'association': association})


@login_required
def generate_league_schedule(request, age_group, tier, season, association_id):
    print(f"=== GENERATE_LEAGUE_SCHEDULE CALLED ===")
    print(f"Params: {age_group}/{tier}/{season}/{association_id}")
    
    # Get the association and validate access
    try:
        association = Association.objects.get(id=association_id)
    except Association.DoesNotExist:
        messages.error(request, "Association not found")
        return redirect('dashboard')
    
    # Check if user is an association admin
    if request.user not in association.admins.all():
        messages.error(request, "You must be an association admin to access the league scheduler")
        return redirect('dashboard')
    
    # Get or create the league scheduling state
    from users.models import LeagueSchedulingState
    from django.utils import timezone
    league_state, created = LeagueSchedulingState.objects.get_or_create(
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
        
        print("=" * 80)
        print("📅 AVAILABILITY DEADLINE UPDATE TRIGGERED")
        print("=" * 80)
        print(f"🏢 Association: {association.name}")
        print(f"📋 League: {age_group} {tier} ({season})")
        print(f"👤 User: {request.user.username} (ID: {request.user.id})")
        print(f"⏰ Old Deadline: {league_state.availability_deadline}")
        print(f"🔧 Old Auto-Schedule: {league_state.auto_schedule_enabled}")
        print(f"📝 New Deadline (raw): {deadline_str}")
        print(f"🔧 New Auto-Schedule: {auto_schedule}")
        print(f"⏰ Timestamp: {timezone.now()}")
        print("=" * 80)
        
        if deadline_str:
            try:
                from datetime import datetime
                
                # Parse the datetime and make it timezone-aware in Pacific time
                deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
                new_deadline = timezone.make_aware(deadline)
                
                print(f"✅ Parsed Deadline (Pacific): {new_deadline}")
                print(f"📊 League State ID: {league_state.id}")
                
                league_state.availability_deadline = new_deadline
                league_state.auto_schedule_enabled = auto_schedule
                # Reset status to 'waiting' so the background scheduler will pick it up
                league_state.status = 'waiting'
                league_state.save()
                
                print(f"💾 League state saved successfully!")
                print(f"   New deadline: {league_state.availability_deadline}")
                print(f"   Auto-schedule: {league_state.auto_schedule_enabled}")
                print(f"   Status reset to: {league_state.status}")
                
                # Create orchestration service and reschedule deadline task
                orchestration_service = SchedulingOrchestrationService(age_group, tier, season, association)
                task_id = orchestration_service.reschedule_deadline_task()
                
                if task_id:
                    print(f"🚀 Background task scheduled with ID: {task_id}")
                    messages.success(request, f"League scheduling settings updated and deadline task scheduled (Task ID: {task_id[:8]}...)!")
                else:
                    print(f"⚠️ No background task scheduled")
                    messages.success(request, "League scheduling settings updated!")
                    
            except ValueError:
                print(f"❌ ERROR: Invalid deadline format: {deadline_str}")
                messages.error(request, "Invalid deadline format. Please use the date picker.")
            except Exception as e:
                print(f"❌ ERROR: {str(e)}")
                messages.error(request, f"Error scheduling deadline task: {str(e)}")
        
        return redirect('league_schedule', age_group=age_group, tier=tier, season=season, association_id=association_id)
      # Get teams in this specific league (age_group + tier + season + association)
    teams = Team.objects.filter(
        age_group=age_group, 
        tier=tier, 
        season=season,
        club__association=association
    )
    
    if not teams.exists():
        messages.error(request, f"No teams found for {age_group} {tier} {season} league")
        return redirect('dashboard')
    
    # Initialize scheduler but don't generate schedule automatically when page is loaded
    scheduler = LeagueScheduler(age_group, tier, season, association)
    
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
    
    # New code to include teams' availability dates with doubleheader info
    teams_with_availability = []
    for team in teams:
        # Get home dates with doubleheader info
        home_date_objects = TeamDate.objects.filter(team=team, is_home=True).values('date', 'allow_doubleheader')
        away_date_objects = TeamDate.objects.filter(team=team, is_home=False).values('date', 'allow_doubleheader')
        teams_with_availability.append({
            'team': team,
            'home_dates': home_date_objects,
            'away_dates': away_date_objects
        })

    if unscheduled_matches:
        messages.warning(
            request, 
            f"Schedule generated with {len(unscheduled_matches)} conflicts that need resolution"
        )
    
    return render(request, 'users/league_schedule.html', {
        'schedule': schedule,
        'unscheduled_matches': unscheduled_matches,
        'age_group': age_group,
        'tier': tier,
        'season': season,
        'association': association,
        'teams_with_availability': teams_with_availability,
        'league_state': league_state,  # Add deadline management context
    })

@login_required
@require_http_methods(["POST"])
@csrf_exempt
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
        print("=== CALLING LEAGUE_SCHEDULER.CREATE_SCHEDULE ===")
        scheduler = LeagueScheduler(age_group, tier, season, association)
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

        # Get or create league state for template context
        from users.models import LeagueSchedulingState
        league_state, created = LeagueSchedulingState.objects.get_or_create(
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
        
        print("=== REDIRECTING TO LEAGUE_SCHEDULE ===")
        # Redirect back to the league schedule page to load fresh data from database
        return redirect('league_schedule', 
                       age_group=age_group, 
                       tier=tier, 
                       season=season, 
                       association_id=association_id)                       
    except Exception as e:
        error_message = str(e)
        print(f"ERROR in generate_schedule_service: {error_message}")
        messages.error(request, f"Error generating schedule: {error_message}")
        return redirect('league_schedule', 
                       age_group=age_group, 
                       tier=tier, 
                       season=season, 
                       association_id=association_id)

@login_required
def league_calendar(request, age_group, tier, season, association_id):
    # Get the association and validate access
    try:
        association = Association.objects.get(id=association_id)
    except Association.DoesNotExist:
        messages.error(request, "Association not found")
        return redirect('dashboard')
    
    # Check if user is an association admin
    if request.user not in association.admins.all():
        messages.error(request, "You must be an association admin to access the league calendar")
        return redirect('dashboard')
      # Get teams in this specific league
    teams = Team.objects.filter(
        age_group=age_group, 
        tier=tier, 
        season=season,
        club__association=association    )
    if not teams.exists():
        messages.error(request, f"No teams found for {age_group} {tier} {season} league")
        return redirect('dashboard')
      # Load existing generated schedule instead of regenerating
    from users.models import GeneratedSchedule, ScheduleMatch
    
    existing_schedule = GeneratedSchedule.objects.filter(
        age_group=age_group,
        tier=tier,
        season=season,
        association=association,
        is_active=True
    ).first()
    
    schedule = []
    if existing_schedule:
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
    return render(request, 'users/league_calendar.html', {
        'schedule': schedule,
        'association': association,
        'age_group': age_group,
        'tier': tier,
        'season': season,
        'events_json': events_json
    })

@login_required
def clubs_list(request, association_id):
    """View clubs for a specific association - only accessible by association admins"""
    try:
        association = Association.objects.get(id=association_id)
    except Association.DoesNotExist:
        messages.error(request, "Association not found")
        return redirect('dashboard')
    
    # Check if user is an association admin
    if request.user not in association.admins.all():
        messages.error(request, "You must be an association admin to view clubs")
        return redirect('dashboard')
    
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
def association_leagues(request, association_id):
    """Show all leagues for an association admin"""
    from users.models import LeagueSchedulingState  # Import at function level
    
    try:
        association = Association.objects.get(id=association_id)
    except Association.DoesNotExist:
        messages.error(request, "Association not found")
        return redirect('dashboard')
      # Check if user is an association admin
    if request.user not in association.admins.all():
        messages.error(request, "You must be an association admin to access this page")
        return redirect('dashboard')
    
    # Handle league settings updates
    if request.method == 'POST':
        if 'update_league_settings' in request.POST:
            # Handle season settings update
            season_start = request.POST.get('season_start')
            season_end = request.POST.get('season_end')
            
            # Store season settings in request.session (you might want to add these fields to Association model later)
            current_settings = request.session.get('league_settings', {})
            current_settings.update({
                'season_start': season_start,
                'season_end': season_end,
            })
            request.session['league_settings'] = current_settings
            
            messages.success(request, "Season settings updated successfully!")
            return redirect('association_leagues', association_id=association_id)
            
        elif 'update_deadline_settings' in request.POST:
            # Handle deadline settings update
            scheduling_deadline = request.POST.get('scheduling_deadline')
            apply_to_all = request.POST.get('apply_deadline_to_all') == 'on'
            
            # Store deadline setting in request.session
            current_settings = request.session.get('league_settings', {})
            current_settings['scheduling_deadline'] = scheduling_deadline
            request.session['league_settings'] = current_settings
            
            if apply_to_all and scheduling_deadline:
                # Update all league scheduling states for this association
                from datetime import datetime
                try:
                    deadline = datetime.strptime(scheduling_deadline, '%Y-%m-%dT%H:%M')
                    deadline_aware = timezone.make_aware(deadline)
                    
                    updated_count = LeagueSchedulingState.objects.filter(
                        association=association
                    ).update(availability_deadline=deadline_aware)
                    
                    messages.success(request, f"Scheduling deadline updated for {updated_count} leagues!")
                except ValueError:
                    messages.error(request, "Invalid deadline format")
            else:
                messages.success(request, "Deadline settings updated successfully!")
            
            return redirect('association_leagues', association_id=association_id)
    
    # Get league settings from session or set defaults
    league_settings = request.session.get('league_settings', {
        'season_start': '',
        'season_end': '',
        'scheduling_deadline': (timezone.now() + timezone.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M')
    })
    
    # Get all unique league combinations for this association
    leagues = Team.objects.filter(club__association=association).values(
        'age_group', 'tier', 'season'
    ).distinct().order_by('season', 'age_group', 'tier')
    
    # Get team counts for each league and scheduling state
    leagues_with_data = []
    for league in leagues:
        teams_in_league = Team.objects.filter(
            club__association=association,
            age_group=league['age_group'],
            tier=league['tier'],
            season=league['season']        )
        
        # Get or create league scheduling state
        league_state, created = LeagueSchedulingState.objects.get_or_create(
            age_group=league['age_group'],
            tier=league['tier'],
            season=league['season'],
            association=association,
            defaults={
                'availability_deadline': timezone.now() + timezone.timedelta(days=30),
                'auto_schedule_enabled': True
            }
        )
        
        leagues_with_data.append({
            'age_group': league['age_group'],
            'tier': league['tier'],
            'season': league['season'],
            'team_count': teams_in_league.count(),
            'league_state': league_state,            'teams': list(teams_in_league.select_related('club').values(
                'id', 'name', 'description', 'location', 'club__name'
            )),
        })
    
    return render(request, 'users/association_leagues.html', {
        'association': association,
        'leagues': leagues_with_data,
        'leagues_json': json.dumps(leagues_with_data, default=str),
        'league_settings': league_settings,  # Add league settings to context
    })