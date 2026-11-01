import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.conf import settings
from files.models import File
from storage.backup_service import check_backup_destination, get_secondary_backup_root

class StorageUsageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Returns storage usage statistics and file count for current user."""
        user = request.user
        used = user.storage_used_bytes
        quota = user.storage_quota_bytes
        percentage = round((used / quota * 100), 2) if quota > 0 else 0.0
        file_count = File.objects(owner=user, deleted=False).count()

        return Response({
            "storage_used_bytes": used,
            "storage_quota_bytes": quota,
            "usage_percentage": percentage,
            "file_count": file_count,
        }, status=status.HTTP_200_OK)

class BackupStatusView(APIView):
    """Returns secondary encrypted backup destination health, location, and replication stats."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sec_root = get_secondary_backup_root()
        dest_check = check_backup_destination(sec_root)

        primary_root = getattr(settings, 'STORAGE_ROOT', '')
        primary_drive = os.path.splitdrive(str(primary_root))[0].upper()
        sec_drive = os.path.splitdrive(str(sec_root))[0].upper()
        same_disk = bool(primary_drive and sec_drive and primary_drive == sec_drive)

        replicated_count = 0
        if dest_check.get("ok"):
            try:
                blobs_dir = sec_root / "blobs"
                if blobs_dir.exists():
                    replicated_count = sum(1 for _ in blobs_dir.glob("*/*"))
            except Exception:
                pass

        return Response({
            "backup_destination": dest_check,
            "primary_storage_path": str(primary_root),
            "secondary_backup_path": str(sec_root),
            "is_same_disk": same_disk,
            "replicated_blobs_count": replicated_count,
        }, status=status.HTTP_200_OK)
