from celery import shared_task
from .coffee_machine import get_coffee_machine
from .models import CoffeeDelivery, MaintenanceLog
from .button_monitor import get_button_monitor
from django.utils import timezone
from django.core.cache import cache
import logging

logger = logging.getLogger('machine')

@shared_task
def deliver_coffee_async(delivery_id):
    """Async coffee delivery task"""
    try:
        delivery = CoffeeDelivery.objects.get(id=delivery_id)
        machine = get_coffee_machine()
        
        if not machine.ensure_connection():
            delivery.status = 'failed'
            delivery.error_message = 'Failed to connect to machine'
            delivery.save()
            return False
        
        # Start delivery
        result = machine.deliver_coffee(delivery.group_number, delivery.coffee_type)
        
        if result['success']:
            delivery.status = 'in_progress'
            delivery.save()
            
            # Wait for completion
            if machine.wait_until_group_is_free(delivery.group_number, timeout=120):
                delivery.status = 'completed'
                delivery.completed_at = timezone.now()
            else:
                delivery.status = 'failed'
                delivery.error_message = 'Delivery timeout'
                
        else:
            delivery.status = 'failed'
            delivery.error_message = result['message']
            
        delivery.save()
        return delivery.status == 'completed'
        
    except Exception as e:
        logger.error(f"Error in async coffee delivery: {e}")
        try:
            delivery = CoffeeDelivery.objects.get(id=delivery_id)
            delivery.status = 'failed'
            delivery.error_message = str(e)
            delivery.save()
        except:
            pass
        return False

@shared_task
def health_check_task():
    """Periodic health check task"""
    try:
        machine = get_coffee_machine()
        health = machine.health_check()
        
        MaintenanceLog.objects.create(
            log_type='health_check',
            message=f'Scheduled health check - Status: {health["overall_status"]}',
            resolved=health['overall_status'] == 'healthy'
        )
        
        return health['overall_status'] == 'healthy'
        
    except Exception as e:
        logger.error(f"Error in health check task: {e}")
        MaintenanceLog.objects.create(
            log_type='health_check',
            message=f'Health check failed: {str(e)}',
            resolved=False
        )
        return False

@shared_task
def monitor_button_presses():
    """
    Continuous monitoring task for physical button presses
    This task should be scheduled to run every 2-3 seconds
    """
    try:
        # Check if monitoring is enabled
        if not cache.get('button_monitoring_enabled', True):
            return {'status': 'disabled', 'message': 'Button monitoring is disabled'}

        monitor = get_button_monitor()
        result = monitor.monitor_single_cycle()

        # Update monitoring status in cache
        cache.set('last_button_monitor_check', timezone.now().isoformat(), timeout=60)

        # Log significant activities
        if result['activities']:
            logger.info(f"Button monitor detected {len(result['activities'])} activities")
            for activity in result['activities']:
                if activity['type'] == 'delivery_started':
                    logger.info(f"Manual delivery started: {activity['coffee_type']} on group {activity['group']}")
                elif activity['type'] == 'delivery_completed':
                    logger.info(f"Manual delivery completed: {activity['coffee_type']} on group {activity['group']}")

        return result

    except Exception as e:
        logger.error(f"Error in button monitoring task: {e}")
        MaintenanceLog.objects.create(
            log_type='connection_issue',
            message=f'Button monitoring error: {str(e)}',
            resolved=False
        )
        return {'status': 'error', 'message': str(e)}

@shared_task
def start_button_monitoring_service():
    """
    Start the button monitoring service
    This should be called once to enable monitoring
    """
    try:
        cache.set('button_monitoring_enabled', True, timeout=None)
        logger.info("Button monitoring service started")

        MaintenanceLog.objects.create(
            log_type='health_check',
            message='Button monitoring service started',
            resolved=True
        )

        return {'status': 'started', 'message': 'Button monitoring service is now active'}

    except Exception as e:
        logger.error(f"Error starting button monitoring service: {e}")
        return {'status': 'error', 'message': str(e)}

@shared_task
def stop_button_monitoring_service():
    """
    Stop the button monitoring service
    """
    try:
        cache.set('button_monitoring_enabled', False, timeout=None)
        logger.info("Button monitoring service stopped")

        MaintenanceLog.objects.create(
            log_type='health_check',
            message='Button monitoring service stopped',
            resolved=True
        )

        return {'status': 'stopped', 'message': 'Button monitoring service is now inactive'}

    except Exception as e:
        logger.error(f"Error stopping button monitoring service: {e}")
        return {'status': 'error', 'message': str(e)}