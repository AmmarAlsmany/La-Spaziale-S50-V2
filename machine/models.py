from django.db import models
from django.utils import timezone

class CoffeeMachine(models.Model):
    """Model to store coffee machine information and status"""
    name = models.CharField(max_length=100, default="LaSpaziale S50-QSS")
    serial_number = models.CharField(max_length=50, blank=True, null=True)
    firmware_version = models.CharField(max_length=20, blank=True, null=True)
    port = models.CharField(max_length=50)
    baudrate = models.IntegerField(default=9600)
    number_of_groups = models.IntegerField(default=3)
    is_connected = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.serial_number})"

class CoffeeDelivery(models.Model):
    """Model to log coffee deliveries"""
    COFFEE_TYPES = [
        ('single_short', 'Single Short'),
        ('single_medium', 'Single Medium'),
        ('single_long', 'Single Long'),
        ('double_short', 'Double Short'),
        ('double_medium', 'Double Medium'),
        ('double_long', 'Double Long'),
        ('purge', 'Purge Cycle'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('stopped', 'Stopped'),
    ]

    TRIGGER_TYPES = [
        ('api', 'API/Web Interface'),
        ('manual', 'Physical Button Press'),
        ('automatic', 'Automatic (Purge/System)'),
    ]

    coffee_type = models.CharField(max_length=20, choices=COFFEE_TYPES)
    group_number = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_TYPES, default='api')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        trigger_info = f" [{self.get_trigger_type_display()}]" if self.trigger_type != 'api' else ""
        return f"{self.get_coffee_type_display()} - Group {self.group_number} ({self.status}){trigger_info}"

class MaintenanceLog(models.Model):
    """Model to log maintenance activities"""
    LOG_TYPES = [
        ('purge', 'Purge'),
        ('cleaning', 'Cleaning'),
        ('sensor_fault', 'Sensor Fault'),
        ('connection_issue', 'Connection Issue'),
        ('manual_stop', 'Manual Stop'),
        ('health_check', 'Health Check'),
        ('manual_delivery', 'Manual Delivery'),
    ]
    
    log_type = models.CharField(max_length=20, choices=LOG_TYPES)
    group_number = models.IntegerField(blank=True, null=True)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        group_info = f" - Group {self.group_number}" if self.group_number else ""
        return f"{self.get_log_type_display()}{group_info} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"