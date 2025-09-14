from django.urls import path
from . import views, views_raw

app_name = 'machine'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/info/', views.machine_info, name='machine_info'),
    path('api/status/', views.machine_status, name='machine_status'),
    path('api/connect/', views.connect_machine, name='connect_machine'),
    path('api/disconnect/', views.disconnect_machine, name='disconnect_machine'),
    path('api/deliver/', views_raw.deliver_coffee_raw, name='deliver_coffee'),
    path('api/deliver_old/', views.deliver_coffee, name='deliver_coffee_old'),
    path('api/stop/', views_raw.stop_delivery_raw, name='stop_delivery'),
    path('api/purge/', views_raw.start_purge_raw, name='start_purge'),
    path('api/stop_old/', views.stop_delivery, name='stop_delivery_old'),
    path('api/purge_old/', views.start_purge, name='start_purge_old'),
    path('api/health/', views.health_check, name='health_check'),
    path('api/history/', views.delivery_history, name='delivery_history'),
    path('api/logs/', views.maintenance_logs, name='maintenance_logs'),
    path('api/test/', views.test_post, name='test_post'),

    # Button monitoring endpoints
    path('api/monitor/start/', views.start_button_monitoring, name='start_button_monitoring'),
    path('api/monitor/stop/', views.stop_button_monitoring, name='stop_button_monitoring'),
    path('api/monitor/status/', views.button_monitoring_status, name='button_monitoring_status'),
    path('api/manual-deliveries/', views.manual_deliveries, name='manual_deliveries'),
]