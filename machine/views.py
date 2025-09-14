from django.shortcuts import render

# Create your views here.
import json
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import CoffeeMachine, CoffeeDelivery, MaintenanceLog
from .coffee_machine import get_coffee_machine, CoffeeMachineException
import logging

logger = logging.getLogger('machine')

def dashboard(request):
    """Main dashboard view"""
    context = {
        'title': 'Coffee Machine Controller',
        'machine_info': cache.get('machine_info', {}),
        'machine_status': cache.get('machine_status', {}),
    }
    return render(request, 'dashboard.html', context)

@api_view(['GET'])
def machine_info(request):
    """Get machine information"""
    try:
        machine = get_coffee_machine()
        
        # Return basic info if not connected
        if not machine.is_connected:
            return Response({
                'serial_number': 'Not Connected',
                'firmware_version': 'Not Connected',
                'number_of_groups': 'Not Connected',
                'is_blocked': 'Unknown',
                'machine_config': None,
                'connection_status': False,
                'port': machine.port,
                'baudrate': machine.baudrate,
                'last_updated': None
            })
        
        info = machine.get_machine_info()
        return Response(info)
    except Exception as e:
        logger.error(f"Error getting machine info: {e}")
        return Response({
            'serial_number': 'Error',
            'firmware_version': 'Error',
            'number_of_groups': 'Error',
            'is_blocked': 'Unknown',
            'machine_config': None,
            'connection_status': False,
            'port': getattr(settings, 'COFFEE_MACHINE_PORT', '/dev/ttyUSB0'),
            'baudrate': getattr(settings, 'COFFEE_MACHINE_BAUDRATE', 9600),
            'last_updated': None,
            'error': str(e)
        })

@api_view(['GET'])
def machine_status(request):
    """Get current machine status"""
    try:
        machine = get_coffee_machine()
        
        # Return empty status if not connected
        if not machine.is_connected:
            return Response({
                'groups': {
                    'group_1': {'is_busy': False, 'sensor_fault': False, 'purge_countdown': 0, 'current_action': 'Not Connected'},
                    'group_2': {'is_busy': False, 'sensor_fault': False, 'purge_countdown': 0, 'current_action': 'Not Connected'},
                    'group_3': {'is_busy': False, 'sensor_fault': False, 'purge_countdown': 0, 'current_action': 'Not Connected'}
                },
                'machine_blocked': False,
                'connection_status': False
            })
        
        machine_status = machine.get_all_groups_status()
        return Response(machine_status)
    except Exception as e:
        logger.error(f"Error getting machine status: {e}")
        return Response({
            'groups': {
                'group_1': {'is_busy': False, 'sensor_fault': False, 'purge_countdown': 0, 'current_action': 'Error'},
                'group_2': {'is_busy': False, 'sensor_fault': False, 'purge_countdown': 0, 'current_action': 'Error'},
                'group_3': {'is_busy': False, 'sensor_fault': False, 'purge_countdown': 0, 'current_action': 'Error'}
            },
            'machine_blocked': False,
            'connection_status': False,
            'error': str(e)
        })

@api_view(['POST'])
def connect_machine(request):
    """Connect to coffee machine"""
    try:
        # Get port and baudrate from request or use defaults
        data = request.data or {}
        port = data.get('port') or settings.COFFEE_MACHINE_PORT
        baudrate = data.get('baudrate') or settings.COFFEE_MACHINE_BAUDRATE
        
        logger.info(f"Attempting to connect to coffee machine on {port} at {baudrate} baud")
        
        # Get machine instance with specified port/baudrate
        machine = get_coffee_machine(port=port, baudrate=baudrate, force_new=True)
        connected = machine.connect()
        
        if connected:
            # Update database record
            try:
                machine_obj, created = CoffeeMachine.objects.get_or_create(
                    port=machine.port,
                    defaults={'baudrate': machine.baudrate}
                )
                
                info = machine.get_machine_info()
                if info:
                    machine_obj.serial_number = info.get('serial_number')
                    machine_obj.firmware_version = info.get('firmware_version')
                    machine_obj.number_of_groups = info.get('number_of_groups', 3)
                    machine_obj.is_connected = True
                    machine_obj.save()
                
                return Response({
                    'success': True,
                    'message': 'Successfully connected to coffee machine',
                    'machine_info': info
                })
            except Exception as db_error:
                logger.error(f"Database error after connection: {db_error}")
                # Connection succeeded but database update failed
                return Response({
                    'success': True,
                    'message': 'Connected to coffee machine (database update failed)',
                    'machine_info': {}
                })
        else:
            logger.warning(f"Failed to connect to coffee machine on {port}")
            return Response(
                {'success': False, 'message': f'Failed to connect to coffee machine on {port} at {baudrate} baud'}, 
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
    except Exception as e:
        logger.error(f"Connection error: {e}", exc_info=True)
        return Response(
            {'success': False, 'error': str(e), 'message': f'Connection error: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
def disconnect_machine(request):
    """Disconnect from coffee machine"""
    try:
        machine = get_coffee_machine()
        machine.disconnect()
        
        # Update database
        CoffeeMachine.objects.filter(port=machine.port).update(is_connected=False)
        
        return Response({
            'success': True,
            'message': 'Successfully disconnected from coffee machine'
        })
    except Exception as e:
        logger.error(f"Disconnection error: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@csrf_exempt
@require_http_methods(['POST'])
def deliver_coffee(request):
    """Deliver coffee - Pure Django version without DRF"""
    try:
        import json
        
        logger.info(f"=== DELIVER COFFEE REQUEST (Pure Django) ===")
        # Try multiple methods to get the data (for proxy compatibility)
        data = None
        body_content = None
        
        # Method 1: Try to read from WSGI input stream for chunked encoding
        if 'chunked' in request.META.get('HTTP_TRANSFER_ENCODING', '').lower():
            logger.info("Detected chunked encoding, trying to read from WSGI input")
            try:
                # Try to read from the WSGI input stream
                wsgi_input = request.META.get('wsgi.input')
                if wsgi_input:
                    # Save current position
                    current_pos = wsgi_input.tell() if hasattr(wsgi_input, 'tell') else None
                    # Try to read
                    if hasattr(wsgi_input, 'seek'):
                        wsgi_input.seek(0)
                    body_content = wsgi_input.read()
                    logger.info(f"Read from WSGI input: {body_content}")
                    # Restore position if possible
                    if current_pos is not None and hasattr(wsgi_input, 'seek'):
                        wsgi_input.seek(current_pos)
            except Exception as e:
                logger.error(f"Failed to read from WSGI input: {e}")
        
        # Method 2: Try request._stream if available
        if not body_content and hasattr(request, '_stream'):
            try:
                stream = request._stream
                if stream and hasattr(stream, 'read'):
                    current_pos = stream.tell() if hasattr(stream, 'tell') else None
                    if hasattr(stream, 'seek'):
                        stream.seek(0)
                    body_content = stream.read()
                    logger.info(f"Read from _stream: {body_content}")
                    if current_pos is not None and hasattr(stream, 'seek'):
                        stream.seek(current_pos)
            except Exception as e:
                logger.error(f"Failed to read from _stream: {e}")
        
        # Method 3: Use request.body if available
        if not body_content and request.body:
            body_content = request.body
            logger.info(f"Using request.body: {body_content}")
        
        # Now try to parse the body content
        if body_content:
            try:
                if isinstance(body_content, bytes):
                    body_str = body_content.decode('utf-8')
                else:
                    body_str = str(body_content)
                logger.info(f"Decoded body string: {body_str}")
                data = json.loads(body_str)
                logger.info(f"Successfully parsed JSON: {data}")
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Failed to parse as JSON: {e}")
                # Try URL-encoded format
                try:
                    from urllib.parse import parse_qs
                    parsed = parse_qs(body_str)
                    data = {k: v[0] if isinstance(v, list) and v else v for k, v in parsed.items()}
                    logger.info(f"Parsed as URL-encoded: {data}")
                except Exception as e2:
                    logger.error(f"Failed to parse as URL-encoded: {e2}")
        
        # Method 2: Try request.POST as fallback
        if not data and request.POST:
            data = dict(request.POST)
            logger.info(f"Using request.POST: {data}")
        
        # If still no data, log everything we can
        if not data:
            data = {}
            logger.error("No data could be parsed from request")
            logger.error(f"request.__dict__: {request.__dict__}")
        
        # Get values from data - handle both string and int types
        group_number = data.get('group_number')
        coffee_type = data.get('coffee_type')
        
        logger.info(f"Deliver coffee request: group={group_number} (type: {type(group_number)}), coffee_type={coffee_type}")
        
        if group_number is None or coffee_type is None:
            logger.warning(f"Missing parameters: group_number={group_number}, coffee_type={coffee_type}")
            logger.warning(f"Available keys in data: {list(data.keys()) if data else []}")
            return JsonResponse(
                {'success': False, 'message': 'group_number and coffee_type are required', 'error': 'Missing parameters'}, 
                status=400
            )
        
        # Convert group_number to int, handling both string and numeric inputs
        try:
            group_number = int(str(group_number))
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to convert group_number: {group_number}, error: {e}")
            return JsonResponse(
                {'success': False, 'message': f'Invalid group_number: {group_number}', 'error': 'Invalid group_number'}, 
                status=400
            )
        
        if not (1 <= group_number <= 3):
            return JsonResponse(
                {'success': False, 'message': f'group_number must be between 1 and 3, got {group_number}', 'error': 'Invalid group_number'}, 
                status=400
            )
        
        # Validate coffee_type
        valid_types = ['single_short', 'single_medium', 'single_long', 'double_short', 'double_medium', 'double_long']
        if coffee_type not in valid_types:
            return JsonResponse(
                {'success': False, 'message': f'Invalid coffee_type: {coffee_type}. Must be one of {valid_types}', 'error': 'Invalid coffee_type'}, 
                status=400
            )
        
        # Create delivery record
        try:
            delivery = CoffeeDelivery.objects.create(
                coffee_type=coffee_type,
                group_number=group_number,
                status='pending'
            )
        except Exception as db_error:
            logger.error(f"Database error creating delivery: {db_error}")
            return JsonResponse(
                {'success': False, 'message': f'Database error: {str(db_error)}', 'error': 'Database error'}, 
                status=500
            )
        
        try:
            machine = get_coffee_machine()
            result = machine.deliver_coffee(int(group_number), coffee_type)
            
            if result['success']:
                delivery.status = 'in_progress'
                delivery.save()
                
                return JsonResponse({
                    'success': True,
                    'message': result['message'],
                    'delivery_id': delivery.id,
                    'result': result
                })
            else:
                delivery.status = 'failed'
                delivery.error_message = result['message']
                delivery.save()
                
                return JsonResponse(
                    {'success': False, 'message': result['message']}, 
                    status=400
                )
                
        except Exception as e:
            delivery.status = 'failed'
            delivery.error_message = str(e)
            delivery.save()
            raise
            
    except Exception as e:
        logger.error(f"Error delivering coffee: {e}")
        return JsonResponse(
            {'error': str(e)}, 
            status=500
        )

@api_view(['POST'])
def stop_delivery(request):
    """Stop ongoing coffee delivery"""
    try:
        data = request.data
        group_number = data.get('group_number')
        
        if not group_number:
            return Response(
                {'error': 'group_number is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        machine = get_coffee_machine()
        success = machine.stop_delivery(int(group_number))
        
        if success:
            # Update any in-progress deliveries
            CoffeeDelivery.objects.filter(
                group_number=group_number,
                status='in_progress'
            ).update(
                status='stopped',
                completed_at=timezone.now()
            )
            
            # Log maintenance action
            MaintenanceLog.objects.create(
                log_type='manual_stop',
                group_number=group_number,
                message=f'Manual stop command sent to group {group_number}'
            )
            
            return Response({
                'success': True,
                'message': f'Stop command sent to group {group_number}'
            })
        else:
            return Response(
                {'success': False, 'message': 'Failed to send stop command'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Error stopping delivery: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
def start_purge(request):
    """Start purge cycle"""
    try:
        data = request.data
        group_number = data.get('group_number')
        
        if not group_number:
            return Response(
                {'error': 'group_number is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        machine = get_coffee_machine()
        success = machine.start_purge(int(group_number))
        
        if success:
            # Log maintenance action
            MaintenanceLog.objects.create(
                log_type='purge',
                group_number=group_number,
                message=f'Purge cycle started for group {group_number}'
            )
            
            return Response({
                'success': True,
                'message': f'Purge cycle started for group {group_number}'
            })
        else:
            return Response(
                {'success': False, 'message': 'Failed to start purge cycle'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Error starting purge: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def health_check(request):
    """Perform health check"""
    try:
        machine = get_coffee_machine()
        health = machine.health_check()
        
        # Log health check
        MaintenanceLog.objects.create(
            log_type='health_check',
            message=f'Health check performed - Status: {health["overall_status"]}',
            resolved=health['overall_status'] == 'healthy'
        )
        
        return Response(health)
        
    except Exception as e:
        logger.error(f"Error during health check: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def delivery_history(request):
    """Get delivery history"""
    try:
        limit = request.GET.get('limit', 50)
        deliveries = CoffeeDelivery.objects.all()[:int(limit)]
        
        data = []
        for delivery in deliveries:
            data.append({
                'id': delivery.id,
                'coffee_type': delivery.get_coffee_type_display(),
                'group_number': delivery.group_number,
                'status': delivery.get_status_display(),
                'trigger_type': delivery.get_trigger_type_display(),
                'started_at': delivery.started_at.isoformat(),
                'completed_at': delivery.completed_at.isoformat() if delivery.completed_at else None,
                'error_message': delivery.error_message,
                'is_manual': delivery.trigger_type == 'manual'
            })
        
        return Response({'deliveries': data})
        
    except Exception as e:
        logger.error(f"Error getting delivery history: {e}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@csrf_exempt
@require_http_methods(['POST'])
def test_post(request):
    """Test endpoint to debug POST data - Pure Django"""
    import json
    logger.info("=== TEST POST ENDPOINT (Pure Django) ===")
    
    response_data = {
        'method': request.method,
        'content_type': request.content_type,
        'headers': dict(request.headers),
        'body_exists': bool(request.body),
        'body_length': len(request.body) if request.body else 0,
        'body_decoded': request.body.decode('utf-8') if request.body else None,
        'request_POST': dict(request.POST),
    }
    
    # Try to parse body
    if request.body:
        try:
            response_data['parsed_json'] = json.loads(request.body.decode('utf-8'))
        except Exception as e:
            response_data['parsed_json'] = None
            response_data['parse_error'] = str(e)
    
    logger.info(f"Test response: {response_data}")
    return JsonResponse(response_data)

@api_view(['GET'])
def maintenance_logs(request):
    """Get maintenance logs"""
    try:
        limit = request.GET.get('limit', 100)
        logs = MaintenanceLog.objects.all()[:int(limit)]
        
        data = []
        for log in logs:
            data.append({
                'id': log.id,
                'log_type': log.get_log_type_display(),
                'group_number': log.group_number,
                'message': log.message,
                'timestamp': log.timestamp.isoformat(),
                'resolved': log.resolved
            })
        
        return Response({'logs': data})
        
    except Exception as e:
        logger.error(f"Error getting maintenance logs: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Button Monitoring API Endpoints

@api_view(['POST'])
def start_button_monitoring(request):
    """Start button monitoring service"""
    try:
        from .tasks import start_button_monitoring_service

        result = start_button_monitoring_service.delay()
        response = result.get(timeout=10)

        if response['status'] == 'started':
            return Response({
                'success': True,
                'message': response['message'],
                'note': 'Ensure the monitor_button_presses task is scheduled in Celery Beat every 2-3 seconds'
            })
        else:
            return Response(
                {'success': False, 'message': response['message']},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    except Exception as e:
        logger.error(f"Error starting button monitoring: {e}")
        return Response(
            {'success': False, 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
def stop_button_monitoring(request):
    """Stop button monitoring service"""
    try:
        from .tasks import stop_button_monitoring_service

        result = stop_button_monitoring_service.delay()
        response = result.get(timeout=10)

        if response['status'] == 'stopped':
            return Response({
                'success': True,
                'message': response['message']
            })
        else:
            return Response(
                {'success': False, 'message': response['message']},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    except Exception as e:
        logger.error(f"Error stopping button monitoring: {e}")
        return Response(
            {'success': False, 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def button_monitoring_status(request):
    """Get button monitoring status"""
    try:
        enabled = cache.get('button_monitoring_enabled', False)
        last_check = cache.get('last_button_monitor_check', None)
        monitor_status = cache.get('button_monitor_status', {})

        return Response({
            'enabled': enabled,
            'last_check': last_check,
            'last_status': monitor_status.get('status', 'Unknown'),
            'active_deliveries': monitor_status.get('active_deliveries', 0),
            'recent_activities': monitor_status.get('activities', [])[-5:] if monitor_status.get('activities') else []
        })

    except Exception as e:
        logger.error(f"Error getting button monitoring status: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def manual_deliveries(request):
    """Get only manual deliveries (physical button presses)"""
    try:
        limit = request.GET.get('limit', 50)
        deliveries = CoffeeDelivery.objects.filter(trigger_type='manual')[:int(limit)]

        data = []
        for delivery in deliveries:
            data.append({
                'id': delivery.id,
                'coffee_type': delivery.get_coffee_type_display(),
                'group_number': delivery.group_number,
                'status': delivery.get_status_display(),
                'started_at': delivery.started_at.isoformat(),
                'completed_at': delivery.completed_at.isoformat() if delivery.completed_at else None,
                'error_message': delivery.error_message
            })

        return Response({
            'manual_deliveries': data,
            'total_count': CoffeeDelivery.objects.filter(trigger_type='manual').count()
        })

    except Exception as e:
        logger.error(f"Error getting manual deliveries: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )