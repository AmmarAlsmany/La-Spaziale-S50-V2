# Button Press Monitoring Setup Guide

## What This Does
This system monitors your coffee machine's physical buttons and automatically saves any manually-made coffee in your database, just like API-triggered deliveries.

## How It Works
1. **Continuous Monitoring** - Polls the machine's status registers every 2-3 seconds
2. **Button Detection** - Detects when status changes from idle to active (someone pressed a button)
3. **Database Logging** - Creates `CoffeeDelivery` records with `trigger_type='manual'`
4. **Lifecycle Tracking** - Monitors from start to completion of each delivery

## Setup Instructions

### 1. Apply Database Migration
```bash
python manage.py migrate machine
```

### 2. Start Celery Workers
```bash
# Start Celery worker
celery -A coffee_machine_controller worker --loglevel=info

# Start Celery Beat scheduler (in another terminal)
celery -A coffee_machine_controller beat --loglevel=info
```

### 3. Configure Celery Beat Schedule
Add this to your `coffee_machine_controller/settings.py`:

```python
# Add to INSTALLED_APPS if not already there
CELERY_BEAT_SCHEDULE = {
    'monitor-button-presses': {
        'task': 'machine.tasks.monitor_button_presses',
        'schedule': 2.0,  # Every 2 seconds
    },
}
```

### 4. Start Button Monitoring

#### Option A: Via API
```bash
curl -X POST http://localhost:8000/api/monitor/start/
```

#### Option B: Via Management Command
```bash
# Test monitoring for 60 seconds
python manage.py monitor_buttons --action test --duration 60

# Start the service
python manage.py monitor_buttons --action start

# Check status
python manage.py monitor_buttons --action status
```

## API Endpoints

### Start/Stop Monitoring
- `POST /api/monitor/start/` - Start monitoring service
- `POST /api/monitor/stop/` - Stop monitoring service
- `GET /api/monitor/status/` - Get monitoring status

### View Manual Deliveries
- `GET /api/manual-deliveries/` - Get only manual deliveries
- `GET /api/history/` - Get all deliveries (now includes `trigger_type` field)

### Example API Response
```json
{
  "manual_deliveries": [
    {
      "id": 123,
      "coffee_type": "Single Long",
      "group_number": 1,
      "status": "Completed",
      "started_at": "2024-09-15T10:30:00Z",
      "completed_at": "2024-09-15T10:31:30Z",
      "error_message": ""
    }
  ],
  "total_count": 25
}
```

## Testing the System

### 1. Test Without Machine Connection
```bash
# This will show connection errors but test the monitoring logic
python manage.py monitor_buttons --action test --duration 30
```

### 2. Test With Machine Connected
```bash
# Connect to machine first
curl -X POST http://localhost:8000/api/connect/

# Start monitoring
python manage.py monitor_buttons --action test --duration 60

# Now press physical buttons on the coffee machine
# You should see messages like:
# "Physical button press detected: single_long on group 1"
# "Manual delivery started: single_long on group 1"
```

### 3. Check Database Records
```bash
# Via Django shell
python manage.py shell

# In shell:
from machine.models import CoffeeDelivery
CoffeeDelivery.objects.filter(trigger_type='manual').order_by('-started_at')[:5]
```

## Database Changes Made

### CoffeeDelivery Model
- Added `trigger_type` field: `'api'`, `'manual'`, `'automatic'`
- Added `'purge'` to coffee types
- Updated `__str__` method to show trigger type

### MaintenanceLog Model
- Added `'manual_delivery'` log type

## Monitoring Components

### 1. `ButtonPressMonitor` Class
- Detects state changes in machine registers
- Creates database records for manual deliveries
- Tracks delivery lifecycle

### 2. Celery Tasks
- `monitor_button_presses()` - Main monitoring task (run every 2s)
- `start_button_monitoring_service()` - Enable monitoring
- `stop_button_monitoring_service()` - Disable monitoring

### 3. Management Command
- `python manage.py monitor_buttons` - CLI interface for testing

## Troubleshooting

### No Button Presses Detected
1. Ensure machine is connected: `curl -X GET http://localhost:8000/api/status/`
2. Check monitoring status: `python manage.py monitor_buttons --action status`
3. Check Celery logs for errors

### Monitoring Not Running
1. Verify Celery Beat is running with the schedule
2. Check `button_monitoring_enabled` cache: should be `True`
3. Start service: `curl -X POST http://localhost:8000/api/monitor/start/`

### Performance Considerations
- Monitoring polls every 2 seconds (configurable)
- Uses Django cache to store state between polls
- Minimal impact on machine communication

## Next Steps
1. Run the setup commands above
2. Test with physical button presses
3. Check the dashboard - manual deliveries now show with "[Physical Button Press]" indicator
4. Monitor the logs for any issues

The system is now ready to track all manual coffee deliveries alongside your API-controlled ones!