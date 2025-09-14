# machine/button_monitor.py
import time
import logging
from datetime import datetime
from typing import Dict, Optional, Set
from django.core.cache import cache
from django.utils import timezone
from .models import CoffeeDelivery, MaintenanceLog
from .coffee_machine import get_coffee_machine, LaSpazialeCoffeeMachine

logger = logging.getLogger('machine.monitor')

class ButtonPressMonitor:
    """Monitor physical button presses on the coffee machine"""

    def __init__(self):
        self.machine = get_coffee_machine()
        self.previous_states = {}  # Track previous state of each group
        self.active_deliveries = {}  # Track ongoing deliveries
        self.status_masks = LaSpazialeCoffeeMachine.STATUS_MASKS

    def get_coffee_type_from_status(self, status_dict: Dict) -> Optional[str]:
        """Convert status bits to coffee type string"""
        if status_dict['single_short']:
            return 'single_short'
        elif status_dict['single_medium']:
            return 'single_medium'
        elif status_dict['single_long']:
            return 'single_long'
        elif status_dict['double_short']:
            return 'double_short'
        elif status_dict['double_medium']:
            return 'double_medium'
        elif status_dict['double_long']:
            return 'double_long'
        elif status_dict['purge']:
            return 'purge'
        return None

    def is_delivery_active(self, status_dict: Dict) -> bool:
        """Check if any delivery is currently active"""
        return any([
            status_dict['single_short'],
            status_dict['single_medium'],
            status_dict['single_long'],
            status_dict['double_short'],
            status_dict['double_medium'],
            status_dict['double_long'],
            status_dict['purge']
        ])

    def detect_button_press(self, group_num: int, current_status: Dict) -> Optional[str]:
        """
        Detect if a button was pressed by comparing current vs previous state
        Returns coffee_type if new delivery detected, None otherwise
        """
        group_key = f"group_{group_num}"
        previous_status = self.previous_states.get(group_key, {})

        # Check if this is a new delivery (was inactive, now active)
        was_active = self.is_delivery_active(previous_status) if previous_status else False
        is_active = self.is_delivery_active(current_status)

        if not was_active and is_active:
            # New delivery started - detect which coffee type
            coffee_type = self.get_coffee_type_from_status(current_status)
            if coffee_type:
                logger.info(f"Physical button press detected: {coffee_type} on group {group_num}")
                return coffee_type

        return None

    def create_manual_delivery_record(self, group_num: int, coffee_type: str) -> CoffeeDelivery:
        """Create database record for manually triggered delivery"""
        delivery = CoffeeDelivery.objects.create(
            coffee_type=coffee_type,
            group_number=group_num,
            status='in_progress',
            trigger_type='manual',
            started_at=timezone.now()
        )

        # Log the manual delivery
        MaintenanceLog.objects.create(
            log_type='manual_delivery' if coffee_type != 'purge' else 'purge',
            group_number=group_num,
            message=f"Manual {coffee_type} delivery started via physical button on group {group_num}"
        )

        logger.info(f"Created manual delivery record: {delivery}")
        return delivery

    def update_delivery_completion(self, group_num: int, delivery: CoffeeDelivery):
        """Mark delivery as completed when machine becomes idle"""
        delivery.status = 'completed'
        delivery.completed_at = timezone.now()
        delivery.save()

        # Log completion
        MaintenanceLog.objects.create(
            log_type='manual_delivery' if delivery.coffee_type != 'purge' else 'purge',
            group_number=group_num,
            message=f"Manual {delivery.coffee_type} delivery completed on group {group_num}"
        )

        logger.info(f"Manual delivery completed: {delivery}")

    def monitor_single_cycle(self) -> Dict:
        """
        Single monitoring cycle - check all groups for button presses
        Returns summary of detected activities
        """
        if not self.machine.ensure_connection():
            logger.warning("Cannot monitor button presses - machine not connected")
            return {'status': 'disconnected', 'activities': []}

        activities = []
        num_groups = self.machine.get_number_of_groups() or 3

        for group_num in range(1, min(num_groups + 1, 5)):  # Max 4 groups
            try:
                # Get current status
                current_status = self.machine.get_group_selection(group_num)
                if current_status is None:
                    continue

                group_key = f"group_{group_num}"

                # Check for new button press (delivery start)
                coffee_type = self.detect_button_press(group_num, current_status)
                if coffee_type:
                    delivery = self.create_manual_delivery_record(group_num, coffee_type)
                    self.active_deliveries[group_key] = delivery
                    activities.append({
                        'type': 'delivery_started',
                        'group': group_num,
                        'coffee_type': coffee_type,
                        'delivery_id': delivery.id
                    })

                # Check for delivery completion
                is_active = self.is_delivery_active(current_status)
                if group_key in self.active_deliveries and not is_active:
                    # Delivery finished
                    delivery = self.active_deliveries[group_key]
                    self.update_delivery_completion(group_num, delivery)
                    del self.active_deliveries[group_key]
                    activities.append({
                        'type': 'delivery_completed',
                        'group': group_num,
                        'coffee_type': delivery.coffee_type,
                        'delivery_id': delivery.id
                    })

                # Update previous state
                self.previous_states[group_key] = current_status.copy()

            except Exception as e:
                logger.error(f"Error monitoring group {group_num}: {e}")
                activities.append({
                    'type': 'error',
                    'group': group_num,
                    'message': str(e)
                })

        return {
            'status': 'active',
            'timestamp': datetime.now().isoformat(),
            'activities': activities,
            'active_deliveries': len(self.active_deliveries)
        }

    def start_monitoring(self, duration_seconds: int = 60, interval_seconds: float = 2.0):
        """
        Start monitoring for a specific duration (for testing)
        """
        logger.info(f"Starting button press monitoring for {duration_seconds}s (interval: {interval_seconds}s)")

        start_time = time.time()
        cycle_count = 0

        while time.time() - start_time < duration_seconds:
            try:
                result = self.monitor_single_cycle()
                cycle_count += 1

                if result['activities']:
                    logger.info(f"Cycle {cycle_count}: {len(result['activities'])} activities detected")
                    for activity in result['activities']:
                        logger.info(f"  - {activity}")

                # Store monitoring status in cache
                cache.set('button_monitor_status', result, timeout=10)

                time.sleep(interval_seconds)

            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                time.sleep(interval_seconds)

        logger.info(f"Monitoring completed after {cycle_count} cycles")
        return cycle_count


# Global monitor instance
_monitor_instance = None

def get_button_monitor() -> ButtonPressMonitor:
    """Get singleton button monitor instance"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = ButtonPressMonitor()
    return _monitor_instance