# machine/management/commands/monitor_buttons.py
from django.core.management.base import BaseCommand
from django.core.cache import cache
from machine.button_monitor import get_button_monitor
from machine.tasks import start_button_monitoring_service, stop_button_monitoring_service
import signal
import sys
import time


class Command(BaseCommand):
    help = 'Monitor physical button presses on the coffee machine'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            choices=['start', 'stop', 'status', 'test'],
            default='test',
            help='Action to perform: start/stop service, check status, or run test'
        )
        parser.add_argument(
            '--duration',
            type=int,
            default=60,
            help='Duration for test monitoring (seconds, default: 60)'
        )
        parser.add_argument(
            '--interval',
            type=float,
            default=2.0,
            help='Monitoring interval (seconds, default: 2.0)'
        )

    def handle_interrupt(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        self.stdout.write(self.style.WARNING('\nMonitoring stopped by user'))
        sys.exit(0)

    def handle(self, *args, **options):
        action = options['action']

        if action == 'start':
            self.start_service()
        elif action == 'stop':
            self.stop_service()
        elif action == 'status':
            self.show_status()
        elif action == 'test':
            self.test_monitoring(options['duration'], options['interval'])

    def start_service(self):
        """Start the button monitoring service"""
        self.stdout.write("Starting button monitoring service...")

        result = start_button_monitoring_service.delay()
        response = result.get(timeout=10)

        if response['status'] == 'started':
            self.stdout.write(
                self.style.SUCCESS(f'✓ {response["message"]}')
            )
            self.stdout.write(
                "Note: The monitoring task must be scheduled in Celery Beat to run every 2-3 seconds:\n"
                "  monitor_button_presses"
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'✗ Failed to start: {response["message"]}')
            )

    def stop_service(self):
        """Stop the button monitoring service"""
        self.stdout.write("Stopping button monitoring service...")

        result = stop_button_monitoring_service.delay()
        response = result.get(timeout=10)

        if response['status'] == 'stopped':
            self.stdout.write(
                self.style.SUCCESS(f'✓ {response["message"]}')
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'✗ Failed to stop: {response["message"]}')
            )

    def show_status(self):
        """Show current monitoring status"""
        enabled = cache.get('button_monitoring_enabled', False)
        last_check = cache.get('last_button_monitor_check', 'Never')
        monitor_status = cache.get('button_monitor_status', {})

        self.stdout.write("Button Monitoring Status:")
        self.stdout.write(f"  Enabled: {'✓ Yes' if enabled else '✗ No'}")
        self.stdout.write(f"  Last Check: {last_check}")

        if monitor_status:
            self.stdout.write(f"  Last Status: {monitor_status.get('status', 'Unknown')}")
            self.stdout.write(f"  Active Deliveries: {monitor_status.get('active_deliveries', 0)}")

            activities = monitor_status.get('activities', [])
            if activities:
                self.stdout.write(f"  Recent Activities: {len(activities)}")
                for activity in activities[-3:]:  # Show last 3
                    self.stdout.write(f"    - {activity}")

    def test_monitoring(self, duration, interval):
        """Test monitoring for a specific duration"""
        self.stdout.write(f"Testing button monitoring for {duration} seconds...")
        self.stdout.write("Press physical buttons on the coffee machine to see detection")
        self.stdout.write("Press Ctrl+C to stop early\n")

        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_interrupt)

        monitor = get_button_monitor()

        try:
            start_time = time.time()
            cycle_count = 0
            total_activities = 0

            while time.time() - start_time < duration:
                result = monitor.monitor_single_cycle()
                cycle_count += 1

                # Show activity
                if result['activities']:
                    total_activities += len(result['activities'])
                    self.stdout.write(
                        self.style.SUCCESS(f"[Cycle {cycle_count}] Detected {len(result['activities'])} activities:")
                    )
                    for activity in result['activities']:
                        if activity['type'] == 'delivery_started':
                            self.stdout.write(
                                f"  ✓ STARTED: {activity['coffee_type']} on Group {activity['group']}"
                            )
                        elif activity['type'] == 'delivery_completed':
                            self.stdout.write(
                                f"  ✓ COMPLETED: {activity['coffee_type']} on Group {activity['group']}"
                            )
                        elif activity['type'] == 'error':
                            self.stdout.write(
                                self.style.ERROR(f"  ✗ ERROR on Group {activity['group']}: {activity['message']}")
                            )
                else:
                    # Show periodic status
                    if cycle_count % 10 == 0:
                        self.stdout.write(f"[Cycle {cycle_count}] Monitoring... (no activity)")

                time.sleep(interval)

            # Summary
            self.stdout.write(f"\nMonitoring completed:")
            self.stdout.write(f"  Duration: {duration} seconds")
            self.stdout.write(f"  Cycles: {cycle_count}")
            self.stdout.write(f"  Total Activities: {total_activities}")

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nMonitoring stopped by user'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Monitoring error: {e}'))