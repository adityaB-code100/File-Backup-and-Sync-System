from datetime import datetime, timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from files.models import File, Folder
from dateutil.parser import parse as parse_date
from cloud_storage.timezone_utils import to_iso_utc

class FileChangesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Returns files & folders updated since timestamp (ISO string or unix timestamp)."""
        since_param = request.query_params.get('since')
        if not since_param:
            return Response({"error": "'since' query parameter is required.", "code": "VALIDATION_ERROR"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Try float/int timestamp (Unix epoch), fall back to ISO-8601 parsing
            try:
                val = float(since_param)
                since_dt = datetime.fromtimestamp(val, timezone.utc)
            except ValueError:
                parsed = parse_date(since_param)
                if parsed.tzinfo is not None:
                    since_dt = parsed.astimezone(timezone.utc)
                else:
                    since_dt = parsed.replace(tzinfo=timezone.utc)
        except Exception as e:
            return Response({"error": f"Invalid timestamp format: {str(e)}", "code": "VALIDATION_ERROR"}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve modified files and folders (MongoDB stores naive UTC datetimes)
        since_utc_naive = since_dt.replace(tzinfo=None)
        changed_files = File.objects(owner=request.user, updated_at__gte=since_utc_naive)
        changed_folders = Folder.objects(owner=request.user, created_at__gte=since_utc_naive)

        file_items = [f.to_dict() for f in changed_files]
        folder_items = [f.to_dict() for f in changed_folders]

        return Response({
            "since": to_iso_utc(since_dt),
            "changes": folder_items + file_items
        }, status=status.HTTP_200_OK)
