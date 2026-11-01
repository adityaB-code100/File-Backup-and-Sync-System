from django.urls import path
from files.views_folders import FolderListCreateView, FolderDetailView, FolderRestoreView, FolderPurgeView

urlpatterns = [
    path('', FolderListCreateView.as_view(), name='folder-list-create'),
    path('<str:id>/', FolderDetailView.as_view(), name='folder-detail'),
    path('<str:id>/restore/', FolderRestoreView.as_view(), name='folder-restore'),
    path('<str:id>/purge/', FolderPurgeView.as_view(), name='folder-purge'),
]
