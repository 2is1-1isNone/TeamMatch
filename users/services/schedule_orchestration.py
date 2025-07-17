from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from users.models import DivisionSchedulingState, Team, SchedulingNotification
from users.services.schedule_service import DivisionScheduler  # Enhanced scheduler with doubleheader support
from users.services.dynamic_schedule_manager import DynamicScheduleManager
import logging

logger = logging.getLogger(__name__)

class SchedulingOrchestrationService:
    """
    Orchestrates the scheduling process by implementing the hybrid scheduling approach:
    - Triggers scheduling when deadline is reached AND all teams have minimum availability
    - Or when manually triggered
    - Sends notifications for conflicts and keeps notifying until resolved
    - Manages the overall scheduling workflow around the core DivisionScheduler
    """
    def __init__(self, age_group, tier, season, association):
        self.age_group = age_group
        self.tier = tier
        self.season = season
        self.association = association
        self.division_state, created = DivisionSchedulingState.objects.get_or_create(
            age_group=age_group,
            tier=tier,
            season=season,
            association=association,
            defaults={
                'availability_deadline': timezone.now() + timezone.timedelta(days=30),
                'auto_schedule_enabled': True            }
        )
    
    def check_and_trigger_scheduling(self, manual_trigger=False):
        """
        Main method to check conditions and trigger scheduling if appropriate
        """
        logger.info(f"🔍 CHECKING SCHEDULING CONDITIONS for {self.age_group} {self.tier} - {self.association.name}")
        logger.info(f"📋 Manual trigger: {manual_trigger}")
        logger.info(f"📅 Current time: {timezone.now()}")
        logger.info(f"⏰ Deadline: {self.division_state.availability_deadline}")
        logger.info(f"🔧 Auto schedule enabled: {self.division_state.auto_schedule_enabled}")
        logger.info(f"📊 Current status: {self.division_state.status}")
        
        if manual_trigger:
            logger.info(f"🔨 MANUAL TRIGGER - Proceeding to schedule generation")
            return self._trigger_scheduling(manual=True)
        
        logger.info(f"🤖 AUTOMATIC TRIGGER - Checking conditions...")
        should_trigger, reason = self.division_state.should_trigger_scheduling()
        logger.info(f"🎯 Should trigger result: {should_trigger}")
        logger.info(f"📝 Reason: {reason}")
        
        if should_trigger:
            logger.info(f"✅ CONDITIONS MET - Proceeding to schedule generation")
            return self._trigger_scheduling(manual=False)
        else:
            logger.info(f"❌ CONDITIONS NOT MET - Scheduling blocked: {reason}")
            return False, reason
    
    def _trigger_scheduling(self, manual=False):
        """
        Execute the scheduling process using your existing DivisionScheduler
        """
        trigger_reason = "MANUAL TRIGGER" if manual else "AUTOMATIC TRIGGER (DEADLINE REACHED)"
        
        print("=" * 80)
        print(f"🚀 SCHEDULE GENERATION STARTED")
        print("=" * 80) 
        print(f"📋 Division: {self.age_group} {self.tier}")
        print(f"🏢 Association: {self.association.name}")
        print(f"📅 Season: {self.season}")
        print(f"🎯 Trigger Type: {trigger_reason}")
        print(f"⏰ Deadline was: {self.division_state.availability_deadline}")
        print(f"🕐 Current time: {timezone.now()}")
        if not manual:
            print(f"🤖 This schedule was triggered AUTOMATICALLY by the background scheduler")
        else:
            print(f"👤 This schedule was triggered MANUALLY by a user")
        print("=" * 80)
        
        # Enhanced logging for deadline-triggered schedule generation
        logger.info(f"🚀 SCHEDULE GENERATION TRIGGERED for {self.age_group} {self.tier} - {self.association.name}")
        logger.info(f"📅 Trigger reason: {trigger_reason}")
        logger.info(f"⏰ Deadline was: {self.division_state.availability_deadline}")
        logger.info(f"🎯 Current time: {timezone.now()}")
        
        # Update state
        self.division_state.status = 'triggered'
        self.division_state.last_schedule_attempt = timezone.now()
        self.division_state.save()
        
        print(f"🔄 Starting schedule generation process using DivisionScheduler...")
        logger.info(f"🔄 Starting schedule generation process using DivisionScheduler...")
        
        # Use your existing scheduler with all required parameters
        print(f"🏗️  Creating DivisionScheduler instance...")
        scheduler = DivisionScheduler(self.age_group, self.tier, self.season, self.association)
        
        print(f"⚙️  Calling scheduler.create_schedule()...")
        schedule, unscheduled_matches = scheduler.create_schedule()
        
        print(f"✅ Schedule generation completed:")
        print(f"   📅 {len(schedule)} matches scheduled")
        print(f"   ⚠️  {len(unscheduled_matches)} unscheduled matches")
        logger.info(f"✅ Schedule generation completed: {len(schedule)} matches scheduled, {len(unscheduled_matches)} unscheduled")
        
        # Save the generated schedule to database (like manual generation does)
        self._save_schedule_to_database(schedule, unscheduled_matches)
        
        if unscheduled_matches:
            return self._handle_scheduling_conflicts(schedule, unscheduled_matches)
        else:
            return self._handle_successful_scheduling(schedule)
    
    def _handle_scheduling_conflicts(self, schedule, unscheduled_matches):
        """
        Handle cases where not all matches could be scheduled
        """
        logger.info(f"Scheduling conflicts found for {self.age_group} {self.tier}: {len(unscheduled_matches)} unmatched")
        
        # Update division state
        self.division_state.status = 'conflicts'
        self.division_state.schedule_generated_at = timezone.now()
        self.division_state.save()
        
        # Identify teams with conflicts
        conflicted_teams = set()
        for match in unscheduled_matches:
            conflicted_teams.add(match['home_team'])
            conflicted_teams.add(match['away_team'])
        
        # Update unmatched teams
        self.division_state.unmatched_teams.set(conflicted_teams)
        
        # Send notifications
        self._send_conflict_notifications(conflicted_teams, unscheduled_matches)
        
        return True, f"Partial schedule generated with {len(unscheduled_matches)} conflicts"
    
    def _handle_successful_scheduling(self, schedule):
        """
        Handle successful complete scheduling
        """
        logger.info(f"Scheduling completed successfully for {self.age_group} {self.tier}")
        
        # Update division state
        self.division_state.status = 'completed'
        self.division_state.schedule_generated_at = timezone.now()
        self.division_state.unmatched_teams.clear()
        self.division_state.save()
        
        # Send success notifications
        teams = Team.objects.filter(
            age_group=self.age_group,
            tier=self.tier,
            association=self.association
        )
        
        for team in teams:
            self._send_notification(
                team,
                'schedule_complete',
                f"Great news! The schedule for {self.age_group} {self.tier} has been successfully generated. "
                f"Check the division schedule to see your team's games."
            )
        
        return True, "Schedule generated successfully"
    
    def _send_conflict_notifications(self, teams, unscheduled_matches):
        """
        Send notifications to teams about scheduling conflicts
        """
        for team in teams:
            # Find specific reasons for this team's conflicts
            team_conflicts = [m for m in unscheduled_matches 
                            if m['home_team'] == team or m['away_team'] == team]
            
            conflict_reasons = set()
            for conflict in team_conflicts:
                if hasattr(conflict, 'reason'):
                    conflict_reasons.add(conflict['reason'])
            
            message = self._build_conflict_message(team, conflict_reasons)
            
            self._send_notification(team, 'schedule_conflict', message)
            self._send_email_notification(team, 'Schedule Conflict - Action Required', message)
    
    def _build_conflict_message(self, team, conflict_reasons):
        """
        Build a detailed message explaining the conflict
        """
        base_message = f"Your team {team.name} has scheduling conflicts that need to be resolved. "
        
        if conflict_reasons:
            base_message += "Issues found:\n"
            for reason in conflict_reasons:
                base_message += f"• {reason}\n"
        
        base_message += (
            "\nPlease add more weekend availability dates to your calendar. "
            "You'll receive daily reminders until sufficient availability is provided."
        )
        
        return base_message
    
    def _send_notification(self, team, notification_type, message):
        """
        Create a notification record
        """
        SchedulingNotification.objects.create(
            division_state=self.division_state,
            team=team,
            notification_type=notification_type,
            message=message        )
    
    def _send_email_notification(self, team, subject, message):
        """
        Send email notification to team admins
        """
        admin_emails = [admin.email for admin in team.admins.all() if admin.email]
        
        if admin_emails:
            try:
                send_mail(
                    subject=f"[{self.association.name}] {subject}",
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=admin_emails,
                    fail_silently=False
                )
                logger.info(f"Email sent to {team.name} admins: {admin_emails}")
                
                # Log the email notification
                from users.models import DivisionLog
                DivisionLog.log_email_notification(
                    age_group=self.age_group,
                    tier=self.tier,
                    season=self.season,
                    association=self.association,
                    notification_type='team_notification',
                    recipients_count=len(admin_emails),
                    user=None,  # System-generated
                    team=team,
                    details=subject
                )
                
            except Exception as e:
                logger.error(f"Failed to send email to {team.name}: {e}")
    
    def _save_schedule_to_database(self, schedule, unscheduled_matches):
        """
        Save the generated schedule to the database, similar to manual generation
        """
        from users.models import GeneratedSchedule, ScheduleMatch
        
        logger.info(f"💾 SAVING GENERATED SCHEDULE TO DATABASE")
          # Delete any existing schedules for this division first (to avoid duplicates)
        existing_schedules = GeneratedSchedule.objects.filter(
            age_group=self.age_group,
            tier=self.tier,
            season=self.season,
            association=self.association
        )
        if existing_schedules.exists():
            logger.info(f"🗑️ Deleting {existing_schedules.count()} existing schedule(s)")
            existing_schedules.delete()        # Get or create a system user for automated generation
        from django.contrib.auth import get_user_model
        User = get_user_model()
        system_user, created = User.objects.get_or_create(
            username='system',
            defaults={
                'email': 'system@teamschedule.local',
                'first_name': 'System',
                'last_name': 'Scheduler',
                'is_active': False,  # System user shouldn't be able to log in
            }
        )
        
        # Create new GeneratedSchedule record
        generated_schedule = GeneratedSchedule.objects.create(
            age_group=self.age_group,
            tier=self.tier,
            season=self.season,
            association=self.association,
            generated_by=system_user,  # Use system user for automated generation
            is_active=True
        )
        logger.info(f"📊 Generated schedule saved with ID: {generated_schedule.id}")
        
        logger.info(f"💾 SAVING {len(schedule)} SCHEDULED MATCHES TO DATABASE")
        # Save all scheduled matches to the database
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
                status='scheduled'
            )
            logger.info(f"  ✅ Match {i}: {match['home_team'].name} vs {match['away_team'].name} saved")
        
        logger.info(f"⚠️ SAVING {len(unscheduled_matches)} UNSCHEDULED MATCHES TO DATABASE")
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
            logger.info(f"  ❌ Unscheduled Match {i}: {match['home_team'].name} vs {match['away_team'].name} - {match.get('reason', 'Scheduling conflict')}")
        
        logger.info(f"💾 SCHEDULE DATABASE SAVE COMPLETE - {len(schedule)} scheduled, {len(unscheduled_matches)} unscheduled")
        return generated_schedule
    
    def send_daily_reminders(self):
        """
        Send daily reminders to teams with unresolved conflicts
        """
        if self.division_state.status != 'conflicts':
            return
        
        # Check if 24 hours have passed since last notification
        if (self.division_state.last_notification_sent and 
            timezone.now() - self.division_state.last_notification_sent < timezone.timedelta(hours=24)):
            return
        
        # Send reminders to unmatched teams
        for team in self.division_state.unmatched_teams.all():
            message = (
                f"Daily Reminder: Your team {team.name} still has scheduling conflicts. "
                f"Please add more weekend availability dates to resolve these issues."
            )
            
            self._send_notification(team, 'insufficient_availability', message)
            self._send_email_notification(team, 'Daily Reminder - Schedule Conflicts', message)
        
        # Update last notification time
        self.division_state.last_notification_sent = timezone.now()
        self.division_state.save()
    
    def check_for_new_availability(self):
        """
        Check if teams have added new availability since last conflict
        If so, re-trigger scheduling
        """
        if self.division_state.status != 'conflicts':
            return
        
        # Check if any team has added dates since last attempt
        teams = Team.objects.filter(
            age_group=self.age_group,
            tier=self.tier,
            association=self.association
        )
        
        new_dates_added = False
        for team in teams:
            recent_dates = team.dates.filter(
                created_at__gt=self.division_state.last_schedule_attempt
            )
            if recent_dates.exists():
                new_dates_added = True
                break
        
        if new_dates_added:
            logger.info(f"New availability detected for {self.age_group} {self.tier}, re-triggering scheduling")
            return self._trigger_scheduling(manual=False)
        
        return False, "No new availability detected"

    def schedule_deadline_task(self):
        """
        Schedule a Celery task to trigger scheduling at the availability deadline
        """
        return DynamicScheduleManager.schedule_division_deadline(self.division_state)
    
    def cancel_deadline_task(self):
        """
        Cancel the scheduled deadline task for this division
        """
        DynamicScheduleManager.cancel_existing_task(self.division_state)
    
    def reschedule_deadline_task(self):
        """
        Reschedule the deadline task (useful when deadline is changed)
        """
        return DynamicScheduleManager.reschedule_division_deadline(self.division_state)

def run_daily_scheduling_checks():
    """
    Function to be called daily (via cron job or scheduled task)
    """
    logger.info("Running daily scheduling checks")
      # Check all active division states
    active_states = DivisionSchedulingState.objects.filter(
        status__in=['waiting', 'conflicts']
    )
    for state in active_states:
        service = SchedulingOrchestrationService(
            state.age_group,
            state.tier,
            state.season,
            state.association
        )
        
        # Check for auto-trigger conditions
        if state.status == 'waiting':
            service.check_and_trigger_scheduling(manual=False)
        
        # Send daily reminders for conflicts
        elif state.status == 'conflicts':
            service.send_daily_reminders()
            service.check_for_new_availability()
