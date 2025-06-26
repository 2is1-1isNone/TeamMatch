from datetime import datetime, timedelta
from users.models import Team, TeamDate, ScheduleProposal
from django.db.models import Q
import random

class DivisionScheduler:
    def __init__(self, age_group, tier, season, association):
        self.age_group = age_group
        self.tier = tier
        self.season = season
        self.association = association
        self.teams = Team.objects.filter(
            age_group=age_group, 
            tier=tier, 
            season=season,
            club__association=association
        )

    def get_required_matchups(self):
        """Generate all required home/away matchups between teams"""
        matchups = []
        teams_list = list(self.teams)
        
        for i, team_a in enumerate(teams_list):
            for team_b in teams_list[i + 1:]:
                # Each pair plays twice: once with A at home, once with B at home
                matchups.append({'home_team': team_a, 'away_team': team_b})
                matchups.append({'home_team': team_b, 'away_team': team_a})
        
        return matchups

    def get_weekend_series(self, dates):
        """Find all adjacent Saturday+Sunday pairs from a list of dates"""
        dates = sorted(dates)
        series = []
        for i in range(len(dates) - 1):
            if (dates[i + 1] - dates[i]).days == 1 and dates[i].weekday() == 5:  # Saturday followed by Sunday
                series.append((dates[i], dates[i + 1]))
        return series

    def get_team_availability(self):
        """Get all team availability data organized by team and home/away"""
        availability = {}
        
        for team in self.teams:
            availability[team.id] = {
                'home_dates': list(TeamDate.objects.filter(
                    team=team, is_home=True
                ).values_list('date', flat=True)),
                'away_dates': list(TeamDate.objects.filter(
                    team=team, is_home=False
                ).values_list('date', flat=True)),
                'home_doubleheader_dates': list(TeamDate.objects.filter(
                    team=team, is_home=True, allow_doubleheader=True
                ).values_list('date', flat=True)),
                'away_doubleheader_dates': list(TeamDate.objects.filter(
                    team=team, is_home=False, allow_doubleheader=True
                ).values_list('date', flat=True))            }
            
        return availability

    def can_schedule_weekend_series(self, home_team_id, away_team_id, weekend_series, scheduled_series):
        """Check if a weekend series can be scheduled between two teams"""
        sat_date, sun_date = weekend_series
        
        # Check if home team is available for home games on both days
        home_availability = self.availability[home_team_id]['home_dates']
        if sat_date not in home_availability or sun_date not in home_availability:
            return False
            
        # Check if away team is available for away games on both days
        away_availability = self.availability[away_team_id]['away_dates']
        if sat_date not in away_availability or sun_date not in away_availability:
            return False
            
        # Check if the home team already has a series on this weekend
        # (A home team can only host one series per weekend)
        for existing_series in scheduled_series:
            existing_weekend = (existing_series['dates'][0], existing_series['dates'][1])
            if existing_weekend == weekend_series:
                if existing_series['home_team'].id == home_team_id:
                    return False
        
        # Check if the away team already has an away series on this weekend
        # They can only have multiple away series if they specifically allow doubleheaders for away games
        away_doubleheader_dates = self.availability[away_team_id]['away_doubleheader_dates']
        away_allows_doubleheader = sat_date in away_doubleheader_dates and sun_date in away_doubleheader_dates
        
        if not away_allows_doubleheader:
            # Away team doesn't allow doubleheaders, so they can only have one away series per weekend
            for existing_series in scheduled_series:
                existing_weekend = (existing_series['dates'][0], existing_series['dates'][1])
                if existing_weekend == weekend_series:
                    if existing_series['away_team'].id == away_team_id:
                        return False
                    
        # Check if this specific matchup already exists
        for existing_series in scheduled_series:
            if (existing_series['home_team'].id == home_team_id and 
                existing_series['away_team'].id == away_team_id):
                return False
                
        # Note: We allow the same away team to play multiple home teams on the same weekend
        # only if they specifically marked those dates as allow_doubleheader=True for away games
        return True
    
    def create_schedule(self):
        """Create the division schedule with doubleheader priority and proper weekend series only"""
        print("=" * 80)
        print("🏒 DIVISION SCHEDULER STARTED - ATTEMPTING TO CREATE SCHEDULE")
        print("=" * 80)
        print(f"📋 Division: {self.age_group} {self.tier}")
        print(f"📅 Season: {self.season}")
        print(f"🏢 Association: {self.association.name}")
        print(f"👥 Teams: {self.teams.count()}")
        for team in self.teams:
            print(f"   - {team.name}")
        print("=" * 80)
        
        teams = list(self.teams)
        if len(teams) < 2:
            print("❌ INSUFFICIENT TEAMS - Need at least 2 teams to create a schedule")
            return [], []
            
        # Get all required matchups
        required_matchups = self.get_required_matchups()
        print(f"📊 Required matchups: {len(required_matchups)}")
        
        # Get team availability
        print("🔍 Analyzing team availability...")
        self.availability = self.get_team_availability()
        
        # Track scheduled series and completed matchups
        scheduled_series = []  # Weekend series
        completed_matchups = set()  # (home_team_id, away_team_id) pairs
        unscheduled_matchups = []
        
        print(f"🚀 Starting scheduling process for {len(required_matchups)} total matchups...")
        print("=" * 40)
        
        # STEP 1: PRIORITY - Handle doubleheader opportunities first
        doubleheader_opportunities = []
        
        for team in teams:
            # Check away doubleheader dates - prioritize these
            away_dh_dates = self.availability[team.id]['away_doubleheader_dates']
            away_dh_series = self.get_weekend_series(away_dh_dates)
            
            for series in away_dh_series:
                doubleheader_opportunities.append({
                    'type': 'away_doubleheader',
                    'team': team,
                    'weekend_series': series,
                    'priority': 1  # Highest priority
                })
                
            # Check home doubleheader dates
            home_dh_dates = self.availability[team.id]['home_doubleheader_dates']
            home_dh_series = self.get_weekend_series(home_dh_dates)
            
            for series in home_dh_series:
                doubleheader_opportunities.append({
                    'type': 'home_doubleheader',
                    'team': team,
                    'weekend_series': series,
                    'priority': 2  # Lower priority than away
                })
        
        # Sort by priority and shuffle within same priority for fairness
        doubleheader_opportunities.sort(key=lambda x: x['priority'])
        random.shuffle(doubleheader_opportunities)
        
        print(f"Found {len(doubleheader_opportunities)} doubleheader opportunities")
        
        # Process doubleheader opportunities
        for opportunity in doubleheader_opportunities:
            weekend_series = opportunity['weekend_series']
            team = opportunity['team']
            
            print(f"\nProcessing {opportunity['type']} for {team.name} on {weekend_series[0].strftime('%m/%d')}-{weekend_series[1].strftime('%m/%d')}")
            
            if opportunity['type'] == 'away_doubleheader':
                # Try to schedule this away team with MULTIPLE DIFFERENT home opponents on same weekend
                potential_opponents = []
                
                for potential_home_team in teams:
                    if potential_home_team == team:
                        continue
                        
                    matchup_key = (potential_home_team.id, team.id)
                    if matchup_key in completed_matchups:
                        continue
                        
                    if self.can_schedule_weekend_series(potential_home_team.id, team.id, weekend_series, scheduled_series):
                        potential_opponents.append(potential_home_team)
                
                print(f"  Found {len(potential_opponents)} potential home opponents")
                
                # Try to schedule with ALL available opponents for true doubleheader
                scheduled_count = 0
                for home_opponent in potential_opponents:
                    matchup_key = (home_opponent.id, team.id)
                    if matchup_key in completed_matchups:
                        continue
                        
                    # Check if this home opponent is still available (not already scheduled this weekend)
                    if self.can_schedule_weekend_series(home_opponent.id, team.id, weekend_series, scheduled_series):
                        scheduled_series.append({
                            'home_team': home_opponent,
                            'away_team': team,
                            'dates': [weekend_series[0], weekend_series[1]],
                            'status': 'scheduled',
                            'is_doubleheader': True
                        })
                        completed_matchups.add((home_opponent.id, team.id))
                        scheduled_count += 1
                        print(f"  ✓ Scheduled away doubleheader: {home_opponent.name} vs {team.name} on {weekend_series[0].strftime('%m/%d')}-{weekend_series[1].strftime('%m/%d')}")
                        
                        # For a true doubleheader, we want maximum 2 opponents
                        if scheduled_count >= 2:
                            break
                            
                if scheduled_count == 0:
                    print(f"  ✗ No opponents available for away doubleheader")
                elif scheduled_count == 1:
                    print(f"  ⚠ Only one opponent available (not a true doubleheader)")
                else:
                    print(f"  ✓ True doubleheader scheduled with {scheduled_count} opponents")
                    
            elif opportunity['type'] == 'home_doubleheader':
                # Try to schedule this home team with an away opponent 
                potential_opponents = []
                
                for potential_away_team in teams:
                    if potential_away_team == team:
                        continue
                        
                    matchup_key = (team.id, potential_away_team.id)
                    if matchup_key in completed_matchups:
                        continue
                        
                    if self.can_schedule_weekend_series(team.id, potential_away_team.id, weekend_series, scheduled_series):
                        potential_opponents.append(potential_away_team)
                
                print(f"  Found {len(potential_opponents)} potential away opponents")
                
                # Schedule with first available opponent
                if potential_opponents:
                    away_opponent = potential_opponents[0]
                    scheduled_series.append({
                        'home_team': team,
                        'away_team': away_opponent,
                        'dates': [weekend_series[0], weekend_series[1]],
                        'status': 'scheduled',
                        'is_doubleheader': True
                    })
                    completed_matchups.add((team.id, away_opponent.id))
                    print(f"  ✓ Scheduled home doubleheader: {team.name} vs {away_opponent.name} on {weekend_series[0].strftime('%m/%d')}-{weekend_series[1].strftime('%m/%d')}")
        
        print(f"\nCompleted doubleheader scheduling. {len(completed_matchups)} matchups scheduled.")
        
        # STEP 2: Schedule remaining matchups with regular weekend series
        
        # Get all possible weekend series for each team
        all_weekend_series = {}
        for team in teams:
            home_dates = self.availability[team.id]['home_dates']
            away_dates = self.availability[team.id]['away_dates']
            
            all_weekend_series[team.id] = {
                'home_series': self.get_weekend_series(home_dates),
                'away_series': self.get_weekend_series(away_dates)
            }
        
        print(f"Available weekend series per team:")
        for team in teams:
            home_count = len(all_weekend_series[team.id]['home_series'])
            away_count = len(all_weekend_series[team.id]['away_series'])
            print(f"  {team.name}: {home_count} home series, {away_count} away series")
        
        # Schedule all required matchups
        for matchup in required_matchups:
            home_team = matchup['home_team']
            away_team = matchup['away_team']
            matchup_key = (home_team.id, away_team.id)
            
            if matchup_key in completed_matchups:
                continue
                
            # Find available weekend series for this matchup
            home_series = all_weekend_series[home_team.id]['home_series']
            away_series = all_weekend_series[away_team.id]['away_series']
            
            # Find overlapping series
            common_series = [s for s in home_series if s in away_series]
            
            print(f"\nScheduling {home_team.name} (home) vs {away_team.name} (away):")
            print(f"  Home team has {len(home_series)} available series")
            print(f"  Away team has {len(away_series)} available series") 
            print(f"  Common series: {len(common_series)}")
            
            # Try to schedule on first available series
            scheduled = False
            for series in common_series:
                if self.can_schedule_weekend_series(home_team.id, away_team.id, series, scheduled_series):
                    # Schedule this weekend series
                    scheduled_series.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'dates': [series[0], series[1]],
                        'status': 'scheduled'
                    })
                    completed_matchups.add(matchup_key)
                    scheduled = True
                    print(f"  ✓ Scheduled on {series[0].strftime('%a %m/%d')} - {series[1].strftime('%a %m/%d')}")
                    break
                else:
                    print(f"  ✗ Cannot schedule on {series[0].strftime('%a %m/%d')} - {series[1].strftime('%a %m/%d')} (conflict)")
                    
            if not scheduled:
                reason = f"No available weekend series found for {home_team.name} (home) vs {away_team.name} (away)"
                if not common_series:
                    reason += " - No overlapping weekend availability"
                else:
                    reason += " - All common weekends already booked"
                    
                unscheduled_matchups.append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'reason': reason
                })
                print(f"  ✗ Could not schedule: {reason}")
        
        print(f"\n🏁 SCHEDULE GENERATION COMPLETED!")
        print("=" * 80)
        print(f"✅ Successfully scheduled: {len(scheduled_series)} weekend series")
        print(f"❌ Could not schedule: {len(unscheduled_matchups)} matchups")
        if unscheduled_matchups:
            print("📋 Unscheduled matchups:")
            for match in unscheduled_matchups:
                print(f"   - {match['home_team'].name} vs {match['away_team'].name}: {match['reason']}")
        else:
            print("🎉 ALL MATCHUPS SUCCESSFULLY SCHEDULED!")
        print("=" * 80)
        
        # Validate that all scheduled items are proper weekend series
        for series in scheduled_series:
            if len(series['dates']) != 2:
                print(f"ERROR: Invalid series with {len(series['dates'])} dates: {series}")
            elif (series['dates'][1] - series['dates'][0]).days != 1:
                print(f"ERROR: Non-adjacent dates in series: {series['dates']}")
            elif series['dates'][0].weekday() != 5:  # Not Saturday
                print(f"ERROR: Series doesn't start on Saturday: {series['dates'][0]}")
        
        return scheduled_series, unscheduled_matchups
