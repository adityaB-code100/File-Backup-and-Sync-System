from django.urls import path
from storage.views import StorageUsageView, BackupStatusView

urlpatterns = [
    path('usage/', StorageUsageView.as_view(), name='storage-usage'),
    path('backup-status/', BackupStatusView.as_view(), name='storage-backup-status'),
]
