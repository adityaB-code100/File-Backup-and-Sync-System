from datetime import datetime
from bson import ObjectId
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from files.models import Folder, File, FileVersion
import mongoengine as me

class FolderListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """List active folders for the authenticated user.
        If parent_id is specified ('root' or ObjectId), filters by parent_folder.
        Otherwise returns all active non-deleted folders owned by user.
        """
        parent_id = request.query_params.get('parent_id')
        qs = Folder.objects(owner=request.user, deleted=False)
        if parent_id:
            if parent_id in ('root', 'null', 'None'):
                qs = qs.filter(parent_folder=None)
            else:
                try:
                    parent = Folder.objects.get(id=ObjectId(parent_id), owner=request.user, deleted=False)
                    qs = qs.filter(parent_folder=parent)
                except Exception:
                    return Response({"results": []}, status=status.HTTP_200_OK)
        return Response({"results": [f.to_dict() for f in qs]}, status=status.HTTP_200_OK)

    def post(self, request):
        """Create folder (name, parent_id)."""
        name = request.data.get('name', '').strip()
        parent_id = request.data.get('parent_id')

        if not name:
            return Response({"error": "Folder name is required.", "code": "VALIDATION_ERROR"}, status=status.HTTP_400_BAD_REQUEST)

        parent_folder = None
        if parent_id and parent_id not in ('root', 'null', 'None'):
            try:
                parent_folder = Folder.objects.get(id=ObjectId(parent_id), owner=request.user, deleted=False)
            except Exception:
                return Response({"error": "Parent folder not found.", "code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        folder = Folder(
            name=name,
            owner=request.user,
            parent_folder=parent_folder,
            created_at=datetime.utcnow()
        )
        folder.save()
        return Response(folder.to_dict(), status=status.HTTP_201_CREATED)

class FolderDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        """Folder metadata + children listing."""
        try:
            folder = Folder.objects.get(id=ObjectId(id), owner=request.user)
        except Exception:
            return Response({"error": "Folder not found.", "code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        subfolders = [f.to_dict() for f in Folder.objects(owner=request.user, parent_folder=folder, deleted=False)]
        files = [f.to_dict() for f in File.objects(owner=request.user, parent_folder=folder, deleted=False)]

        res = folder.to_dict()
        res['children'] = subfolders + files
        return Response(res, status=status.HTTP_200_OK)

    def patch(self, request, id):
        """Rename or move folder."""
        try:
            folder = Folder.objects.get(id=ObjectId(id), owner=request.user)
        except Exception:
            return Response({"error": "Folder not found.", "code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        if 'name' in request.data:
            new_name = request.data['name'].strip()
            if new_name:
                folder.name = new_name

        if 'parent_id' in request.data:
            parent_id = request.data['parent_id']
            if not parent_id or parent_id in ('root', 'null', 'None'):
                folder.parent_folder = None
            else:
                try:
                    target_parent = Folder.objects.get(id=ObjectId(parent_id), owner=request.user, deleted=False)
                    if str(target_parent.id) == str(folder.id):
                        return Response({"error": "Folder cannot be its own parent.", "code": "VALIDATION_ERROR"}, status=status.HTTP_400_BAD_REQUEST)
                    folder.parent_folder = target_parent
                except Exception:
                    return Response({"error": "Target parent folder not found.", "code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        folder.save()
        return Response(folder.to_dict(), status=status.HTTP_200_OK)

    def delete(self, request, id):
        """Soft-delete folder and all contained subfolders/files."""
        try:
            folder = Folder.objects.get(id=ObjectId(id), owner=request.user)
        except Exception:
            return Response({"error": "Folder not found.", "code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        # Soft delete folder and recursively soft delete child folders & files
        def soft_delete_recursive(f_obj):
            f_obj.deleted = True
            f_obj.save()
            for child_folder in Folder.objects(owner=request.user, parent_folder=f_obj):
                soft_delete_recursive(child_folder)
            for child_file in File.objects(owner=request.user, parent_folder=f_obj):
                child_file.deleted = True
                child_file.save()

        soft_delete_recursive(folder)
        return Response({"detail": "Folder and contents moved to trash."}, status=status.HTTP_200_OK)


class FolderRestoreView(APIView):
    """Restore a soft-deleted folder from trash."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        try:
            folder = Folder.objects.get(id=ObjectId(id), owner=request.user)
        except Exception:
            return Response({"error": "Folder not found.", "code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        if not folder.deleted:
            return Response(
                {"error": "Folder is not in trash.", "code": "NOT_IN_TRASH"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # If the parent folder is also deleted, restore to root to avoid orphaning.
        if folder.parent_folder:
            try:
                parent = Folder.objects.get(id=folder.parent_folder.id)
                if parent.deleted:
                    folder.parent_folder = None
            except Exception:
                folder.parent_folder = None

        folder.deleted = False
        folder.save()
        return Response(folder.to_dict(), status=status.HTTP_200_OK)


class FolderPurgeView(APIView):
    """Permanently delete a folder that is already in trash, including all children.

    NOTE: This view deletes File and FileVersion MongoDB documents only.
    Encrypted blob files on disk are NOT deleted here — a separate background garbage
    collection process should clean orphaned blobs (storage_path entries with no
    referencing FileVersion document).
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, id):
        try:
            folder = Folder.objects.get(id=ObjectId(id), owner=request.user)
        except Exception:
            return Response({"error": "Folder not found.", "code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        if not folder.deleted:
            return Response(
                {"error": "Only trashed folders can be permanently deleted. Move to trash first.", "code": "NOT_IN_TRASH"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Recursively collect all child folder IDs and file IDs
        def _collect_descendants(f_obj, folder_ids, file_ids):
            folder_ids.append(f_obj.id)
            for child_folder in Folder.objects(owner=request.user, parent_folder=f_obj):
                _collect_descendants(child_folder, folder_ids, file_ids)
            for child_file in File.objects(owner=request.user, parent_folder=f_obj):
                file_ids.append(child_file.id)

        folder_ids = []
        file_ids = []
        _collect_descendants(folder, folder_ids, file_ids)

        # Delete FileVersion documents for collected files
        # (blobs on disk are NOT deleted — handled by GC)
        FileVersion.objects(file__in=file_ids).delete()

        # Delete File documents
        File.objects(id__in=file_ids).delete()

        # Delete Folder documents
        Folder.objects(id__in=folder_ids).delete()

        return Response(
            {"detail": f"Folder and {len(file_ids)} file(s) permanently deleted."},
            status=status.HTTP_200_OK
        )
