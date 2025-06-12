from datetime import datetime
from users.models import Team, TeamDate, ScheduleProposal
from django.db.models import Q

class LeagueScheduler:
    def __init__(self, age_group, tier):
        self.age_group = age_group
        self.tier = tier
        self.teams = Team.objects.filter(age_group=age_group, tier=tier)
        self.schedule_conflicts = []

    def get_team_pairings(self):
        """Generate all required home/away pairings between teams"""
        pairings = []
        teams_list = list(self.teams)
        for i, home_team in enumerate(teams_list):
            for away_team in teams_list[i + 1:]:
                # Each team needs to play each other twice (home and away)
                pairings.append((home_team, away_team))
                pairings.append((away_team, home_team))
        return pairings

    def find_matching_dates(self, home_team, away_team):
        """Find dates that work for both teams and identify reasons for no matches"""
        home_dates = TeamDate.objects.filter(
            team=home_team, 
            is_home=True
        ).values_list('date', flat=True)
        
        away_dates = TeamDate.objects.filter(
            team=away_team, 
            is_home=False
        ).values_list('date', flat=True)

        # Find dates that work for both teams
        matching_dates = set(home_dates).intersection(set(away_dates))

        if not matching_dates:
            # Determine reasons for no matches
            home_team_needs_dates = len(home_dates) == 0
            away_team_needs_dates = len(away_dates) == 0

            return {
                'matching_dates': None,
                'home_team_needs_dates': home_team_needs_dates,
                'away_team_needs_dates': away_team_needs_dates
            }        # Group into weekend pairs for series
        weekend_pairs = []
        sorted_dates = sorted(list(matching_dates))
        for i in range(len(sorted_dates) - 1):
            if (sorted_dates[i + 1] - sorted_dates[i]).days == 1:
                weekend_pairs.append((sorted_dates[i], sorted_dates[i + 1]))

        return {
            'matching_dates': weekend_pairs,
            'home_team_needs_dates': False,
            'away_team_needs_dates': False
        }

    def create_schedule(self):
        """Create the league schedule prioritizing doubleheader dates, then series logic"""
        teams = list(self.teams)
        schedule = []
        unscheduled_matches = []
        scheduled_team_dates = {}  # Track which team-date combinations are used

        # Initialize tracking for team availability
        for team in teams:
            scheduled_team_dates[team.id] = set()

        # Helper: get all possible series (adjacent Sat/Sun) from a list of dates
        def get_series(dates):
            dates = sorted(dates)
            return [
                (dates[i], dates[i+1])
                for i in range(len(dates)-1)
                if (dates[i+1] - dates[i]).days == 1
            ]

        # Helper: check if a team can play on a date (not already scheduled)
        def can_team_play(team_id, date):
            return date not in scheduled_team_dates[team_id]

        # Helper: mark a team as scheduled on a date
        def schedule_team_date(team_id, date):
            scheduled_team_dates[team_id].add(date)        # Step 1: PRIORITIZE DOUBLEHEADER SCHEDULING
        from users.models import TeamDate
        import random
        
        # Find ALL possible doubleheader series across all teams
        all_doubleheader_opportunities = []
        
        for team in teams:
            # Get home doubleheader dates and find weekend series
            home_dh_dates = list(TeamDate.objects.filter(
                team=team, 
                is_home=True, 
                allow_doubleheader=True
            ).values_list('date', flat=True))
            
            # Get away doubleheader dates and find weekend series  
            away_dh_dates = list(TeamDate.objects.filter(
                team=team, 
                is_home=False, 
                allow_doubleheader=True
            ).values_list('date', flat=True))
            
            # Convert to weekend series (adjacent days)
            home_dh_series = get_series(home_dh_dates)
            away_dh_series = get_series(away_dh_dates)
            
            # Add home doubleheader opportunities
            for dh_series in home_dh_series:
                all_doubleheader_opportunities.append({
                    'host_team': team,
                    'series_dates': dh_series,
                    'type': 'home'
                })
            
            # Add away doubleheader opportunities  
            for dh_series in away_dh_series:
                all_doubleheader_opportunities.append({
                    'away_team': team,
                    'series_dates': dh_series,
                    'type': 'away'
                })

        # Debug: Print what doubleheader opportunities we found
        print(f"Found {len(all_doubleheader_opportunities)} total doubleheader opportunities:")
        for opp in all_doubleheader_opportunities:
            if opp['type'] == 'home':
                print(f"  {opp['host_team'].name} wants to HOST doubleheader on {opp['series_dates']}")
            else:
                print(f"  {opp['away_team'].name} wants to TRAVEL for doubleheader on {opp['series_dates']}")

        # Randomly shuffle opportunities to give fair priority when multiple teams want doubleheaders
        random.shuffle(all_doubleheader_opportunities)        # Try to schedule each doubleheader opportunity
        for opportunity in all_doubleheader_opportunities:
            series_dates = opportunity['series_dates']
            print(f"Processing doubleheader opportunity: {opportunity}")
            
            if opportunity['type'] == 'home':
                host_team = opportunity['host_team']
                
                # Check if both days are still available for host team
                if not (can_team_play(host_team.id, series_dates[0]) and can_team_play(host_team.id, series_dates[1])):
                    continue
                    
                # Find opponents available for away games on BOTH days of this series
                potential_opponents = []
                for opponent in teams:
                    if opponent == host_team:
                        continue
                        
                    # Check if opponent can play away on both days
                    opponent_away_dates = set(TeamDate.objects.filter(
                        team=opponent, 
                        is_home=False
                    ).values_list('date', flat=True))
                    
                    if (can_team_play(opponent.id, series_dates[0]) and 
                        can_team_play(opponent.id, series_dates[1]) and
                        series_dates[0] in opponent_away_dates and 
                        series_dates[1] in opponent_away_dates):
                        potential_opponents.append(opponent)
                
                print(f"  For {host_team.name} home DH series {series_dates}: Found {len(potential_opponents)} potential opponents")
                  # Schedule ONE opponent for the full weekend series
                if potential_opponents:
                    opponent = potential_opponents[0]  # Take first available opponent
                    
                    # Check if this pairing hasn't been scheduled yet
                    already_scheduled = any(
                        (m['home_team'] == host_team and m['away_team'] == opponent) or
                        (m['home_team'] == opponent and m['away_team'] == host_team)
                        for m in schedule
                    )
                    
                    if not already_scheduled:
                        schedule.append({
                            'home_team': host_team,
                            'away_team': opponent,
                            'dates': list(series_dates),  # Full weekend series
                            'status': 'scheduled',
                            'type': 'doubleheader_home_series'
                        })                        # Mark both dates as used for both teams
                        schedule_team_date(host_team.id, series_dates[0])
                        schedule_team_date(host_team.id, series_dates[1])
                        schedule_team_date(opponent.id, series_dates[0])
                        schedule_team_date(opponent.id, series_dates[1])
                        print(f"    Scheduled DH home series: {host_team.name} vs {opponent.name} on {series_dates}")
                        break  # Move to next opportunity
                        
            elif opportunity['type'] == 'away':
                print(f"Processing AWAY doubleheader opportunity...")
                away_team = opportunity['away_team']
                series_dates = opportunity['series_dates']
                
                # Check if both days are still available for away team
                if not (can_team_play(away_team.id, series_dates[0]) and can_team_play(away_team.id, series_dates[1])):
                    continue
                    
                print(f"  For {away_team.name} away DH series {series_dates}: Finding opponents available for BOTH days")
                
                # Find opponents available for home games on BOTH days of this series
                potential_opponents = []
                for opponent in teams:
                    if opponent == away_team:
                        continue
                        
                    # Check if opponent can play home on BOTH days
                    opponent_home_dates = set(TeamDate.objects.filter(
                        team=opponent, 
                        is_home=True
                    ).values_list('date', flat=True))
                    
                    if (can_team_play(opponent.id, series_dates[0]) and 
                        can_team_play(opponent.id, series_dates[1]) and
                        series_dates[0] in opponent_home_dates and 
                        series_dates[1] in opponent_home_dates):
                        potential_opponents.append(opponent)
                
                print(f"    Found {len(potential_opponents)} opponents available for BOTH days: {[t.name for t in potential_opponents]}")                # Schedule ALL available opponents for individual games on each day (true doubleheader)
                if potential_opponents:
                    games_scheduled = 0
                    for opponent in potential_opponents:
                        # Check if this pairing hasn't been scheduled yet
                        already_scheduled = any(
                            (m['home_team'] == opponent and m['away_team'] == away_team) or
                            (m['home_team'] == away_team and m['away_team'] == opponent)
                            for m in schedule
                        )
                        
                        if not already_scheduled:
                            # Schedule as a single doubleheader series with both dates
                            schedule.append({
                                'home_team': opponent,
                                'away_team': away_team,
                                'dates': list(series_dates),  # Both dates in one entry
                                'status': 'scheduled',
                                'type': 'doubleheader_away_series'
                            })
                            
                            # Mark both dates as used for the opponent (they host both days)
                            schedule_team_date(opponent.id, series_dates[0])
                            schedule_team_date(opponent.id, series_dates[1])
                            print(f"    Scheduled DH series: {opponent.name} vs {away_team.name} on {series_dates[0]} and {series_dates[1]}")
                            games_scheduled += 1  # One series scheduled (containing 2 games)
                    
                    # Mark the away team's dates as used after scheduling all their doubleheader games
                    if games_scheduled > 0:
                        schedule_team_date(away_team.id, series_dates[0])
                        schedule_team_date(away_team.id, series_dates[1])
                        print(f"    Total doubleheader series scheduled for {away_team.name}: {games_scheduled}")
                else:
                    print(f"    No opponents available for both days - no doubleheader scheduled")

        # Step 2: SCHEDULE REMAINING GAMES USING SERIES LOGIC
        # Build a dict of team id to available home/away series (excluding already scheduled dates)
        team_series = {}
        for team in teams:
            available_home_dates = [
                d for d in TeamDate.objects.filter(team=team, is_home=True).values_list('date', flat=True)
                if can_team_play(team.id, d)
            ]
            available_away_dates = [
                d for d in TeamDate.objects.filter(team=team, is_home=False).values_list('date', flat=True) 
                if can_team_play(team.id, d)
            ]
            
            team_series[team.id] = {
                'home': get_series(available_home_dates),
                'away': get_series(available_away_dates)
            }

        # Schedule remaining pairings using series logic
        for home_team in teams:
            for away_team in teams:
                if home_team == away_team:
                    continue
                    
                # Check if this pairing is already scheduled
                already_scheduled = any(
                    m['home_team'] == home_team and m['away_team'] == away_team
                    for m in schedule
                )
                
                if already_scheduled:
                    continue
                
                # Find available series for this pairing
                possible_series = [
                    s for s in team_series[home_team.id]['home']
                    if s in team_series[away_team.id]['away'] and
                    can_team_play(home_team.id, s[0]) and can_team_play(home_team.id, s[1]) and
                    can_team_play(away_team.id, s[0]) and can_team_play(away_team.id, s[1])
                ]
                
                if possible_series:
                    series = possible_series[0]  # Take the first available series
                    schedule.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'dates': series,
                        'status': 'scheduled',
                        'type': 'series'
                    })
                    # Mark both dates as used for both teams
                    schedule_team_date(home_team.id, series[0])
                    schedule_team_date(home_team.id, series[1])
                    schedule_team_date(away_team.id, series[0])
                    schedule_team_date(away_team.id, series[1])
                else:
                    # Determine reason for failure
                    home_series = team_series[home_team.id]['home']
                    away_series = team_series[away_team.id]['away']
                    
                    if not home_series:
                        reason = f"Home team '{home_team.name}' does not have enough available adjacent dates for a home series."
                    elif not away_series:
                        reason = f"Away team '{away_team.name}' does not have enough available adjacent dates for an away series."
                    elif not any(s in away_series for s in home_series):
                        reason = f"No overlapping series: Home team '{home_team.name}' and away team '{away_team.name}' do not have any matching available weekend series."
                    else:
                        reason = f"All possible series for this matchup are already booked by one or both teams."
                        
                    unscheduled_matches.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'reason': reason
                    })

        return schedule, unscheduled_matches