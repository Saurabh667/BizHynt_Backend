import re
import uuid
import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Q

from api.models import File, FileFolder, FileFolderAssignment, User
from api.permissions import IsAuthenticated, IsSuperAdminUser
from api.helpers import safe_user
from api.s3_util import s3_upload, s3_delete, s3_get_download_url, s3_get_view_url


def resolve_owner_id(user, requested_owner_id=None):
    if user.role != 'super_admin':
        if requested_owner_id is not None and requested_owner_id != user.id:
            raise PermissionError('You cannot access another user section.')
        return user.id
    owner_id = requested_owner_id if requested_owner_id is not None else user.id
    if not User.objects.filter(id=owner_id).exists():
        raise ValueError('Section user not found.')
    return owner_id


def parse_optional_id(val):
    if val is None or val == '':
        return None
    try:
        parsed = int(val)
        if parsed < 1:
            return None
        return parsed
    except (ValueError, TypeError):
        return None


class FileUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        file = request.FILES.get('file')
        if not file:
            return Response({'success': False, 'message': 'Please select a file.'}, status=status.HTTP_400_BAD_REQUEST)

        original_name = os.path.basename(file.name.replace('\\', '/'))[:255]
        if not original_name:
            return Response({'success': False, 'message': 'Invalid filename.'}, status=status.HTTP_400_BAD_REQUEST)

        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', original_name)
        key = f"files/{user.id}/{uuid.uuid4()}-{safe_name}"

        content_type = file.content_type or 'application/octet-stream'
        file_bytes = file.read()

        try:
            s3_upload(key, file_bytes, content_type)
        except Exception as e:
            return Response({'success': False, 'message': f'S3 upload failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            saved_file = File.objects.create(
                original_name=original_name,
                s3_key=key,
                mime_type=content_type,
                size=file.size,
                uploaded_by=user
            )
            return Response({
                'id': saved_file.id,
                'originalName': saved_file.original_name,
                's3Key': saved_file.s3_key,
                'mimeType': saved_file.mime_type,
                'size': str(saved_file.size),
                'uploadedById': saved_file.uploaded_by_id,
                'uploadedAt': saved_file.uploaded_at.isoformat() if saved_file.uploaded_at else None,
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            s3_delete(key)
            return Response({'success': False, 'message': f'Failed to save file record: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FileFolderUsersView(APIView):
    permission_classes = [IsSuperAdminUser]

    def get(self, request):
        users = User.objects.filter(is_active=True).values('id', 'name', 'email', 'role').order_by('name')
        return Response(list(users))


class FileListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        requested_owner_id = parse_optional_id(request.query_params.get('ownerId'))

        try:
            owner_id = resolve_owner_id(user, requested_owner_id)
        except (PermissionError, ValueError) as err:
            return Response({'success': False, 'message': str(err)}, status=status.HTTP_403_FORBIDDEN)

        q_filter = Q()
        if user.role != 'super_admin':
            q_filter &= Q(uploaded_by_id=user.id)
        else:
            uploaded_by_id = parse_optional_id(request.query_params.get('uploadedById'))
            if uploaded_by_id:
                q_filter &= Q(uploaded_by_id=uploaded_by_id)

        search = request.query_params.get('search', '').strip()
        if search:
            q_filter &= Q(original_name__icontains=search)

        folder_id_param = request.query_params.get('folderId')
        if folder_id_param is not None:
            if folder_id_param == '0' or folder_id_param == '':
                # Unassigned to any folder for this owner
                assigned_file_ids = FileFolderAssignment.objects.filter(owner_id=owner_id).values_list('file_id', flat=True)
                q_filter &= ~Q(id__in=assigned_file_ids)
            else:
                try:
                    f_id = int(folder_id_param)
                    if not FileFolder.objects.filter(id=f_id, owner_id=owner_id).exists():
                        return Response({'success': False, 'message': 'Folder not found.'}, status=status.HTTP_404_NOT_FOUND)
                    assigned_file_ids = FileFolderAssignment.objects.filter(owner_id=owner_id, folder_id=f_id).values_list('file_id', flat=True)
                    q_filter &= Q(id__in=assigned_file_ids)
                except ValueError:
                    return Response({'success': False, 'message': 'Invalid folder ID.'}, status=status.HTTP_400_BAD_REQUEST)

        files = File.objects.filter(q_filter).select_related('uploaded_by').order_by('-uploaded_at')

        results = []
        for f in files:
            results.append({
                'id': f.id,
                'originalName': f.original_name,
                's3Key': f.s3_key,
                'mimeType': f.mime_type,
                'size': str(f.size),
                'uploadedById': f.uploaded_by_id,
                'uploadedAt': f.uploaded_at.isoformat() if f.uploaded_at else None,
                'uploadedBy': {
                    'id': f.uploaded_by.id,
                    'name': f.uploaded_by.name,
                    'email': f.uploaded_by.email,
                }
            })

        return Response(results)


class FileDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        user = request.user
        file = File.objects.filter(id=id).first()
        if not file:
            return Response({'success': False, 'message': 'File not found.'}, status=status.HTTP_404_NOT_FOUND)

        if user.role != 'super_admin' and file.uploaded_by_id != user.id:
            return Response({'success': False, 'message': 'You cannot access this file.'}, status=status.HTTP_403_FORBIDDEN)

        url = s3_get_download_url(file.s3_key, file.original_name)
        return Response({'url': url, 'expiresIn': 60})


class FileViewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        user = request.user
        file = File.objects.filter(id=id).first()
        if not file:
            return Response({'success': False, 'message': 'File not found.'}, status=status.HTTP_404_NOT_FOUND)

        if user.role != 'super_admin' and file.uploaded_by_id != user.id:
            return Response({'success': False, 'message': 'You cannot access this file.'}, status=status.HTTP_403_FORBIDDEN)

        url = s3_get_view_url(file.s3_key, file.original_name, file.mime_type or 'application/octet-stream')
        return Response({'url': url, 'expiresIn': 60})


class FileDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, id):
        user = request.user
        file = File.objects.filter(id=id).first()
        if not file:
            return Response({'success': False, 'message': 'File not found.'}, status=status.HTTP_404_NOT_FOUND)

        if user.role != 'super_admin' and file.uploaded_by_id != user.id:
            return Response({'success': False, 'message': 'You cannot access this file.'}, status=status.HTTP_403_FORBIDDEN)

        s3_delete(file.s3_key)
        file.delete()
        return Response({'message': 'File deleted successfully.'})


class FolderListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        requested_owner_id = parse_optional_id(request.query_params.get('ownerId'))

        try:
            owner_id = resolve_owner_id(user, requested_owner_id)
        except (PermissionError, ValueError) as err:
            return Response({'success': False, 'message': str(err)}, status=status.HTTP_403_FORBIDDEN)

        parent_id_param = request.query_params.get('parentId')
        parent_id = parse_optional_id(parent_id_param)

        folders = FileFolder.objects.filter(
            owner_id=owner_id, parent_id=parent_id
        ).annotate(
            children_count=Count('children', distinct=True),
            assignments_count=Count('assignments', distinct=True)
        ).order_by('name')

        results = []
        for f in folders:
            results.append({
                'id': f.id,
                'name': f.name,
                'ownerId': f.owner_id,
                'parentId': f.parent_id,
                'createdAt': f.created_at.isoformat() if f.created_at else None,
                'updatedAt': f.updated_at.isoformat() if f.updated_at else None,
                '_count': {
                    'children': f.children_count,
                    'assignments': f.assignments_count,
                }
            })

        return Response(results)

    def post(self, request):
        user = request.user
        requested_owner_id = parse_optional_id(request.query_params.get('ownerId'))

        try:
            owner_id = resolve_owner_id(user, requested_owner_id)
        except (PermissionError, ValueError) as err:
            return Response({'success': False, 'message': str(err)}, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get('name', '').strip()
        if not name:
            return Response({'success': False, 'message': 'Folder name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        parent_id = parse_optional_id(request.data.get('parentId'))
        if parent_id and not FileFolder.objects.filter(id=parent_id, owner_id=owner_id).exists():
            return Response({'success': False, 'message': 'Parent folder not found.'}, status=status.HTTP_404_NOT_FOUND)

        folder = FileFolder.objects.create(
            name=name,
            owner_id=owner_id,
            parent_id=parent_id
        )

        return Response({
            'id': folder.id,
            'name': folder.name,
            'ownerId': folder.owner_id,
            'parentId': folder.parent_id,
            'createdAt': folder.created_at.isoformat() if folder.created_at else None,
            'updatedAt': folder.updated_at.isoformat() if folder.updated_at else None,
        }, status=status.HTTP_201_CREATED)


class FolderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        user = request.user
        requested_owner_id = parse_optional_id(request.query_params.get('ownerId'))

        try:
            owner_id = resolve_owner_id(user, requested_owner_id)
        except (PermissionError, ValueError) as err:
            return Response({'success': False, 'message': str(err)}, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get('name', '').strip()
        if not name:
            return Response({'success': False, 'message': 'Folder name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        folder = FileFolder.objects.filter(id=id, owner_id=owner_id).first()
        if not folder:
            return Response({'success': False, 'message': 'Folder not found.'}, status=status.HTTP_404_NOT_FOUND)

        folder.name = name
        folder.save(update_fields=['name'])

        return Response({
            'id': folder.id,
            'name': folder.name,
            'ownerId': folder.owner_id,
            'parentId': folder.parent_id,
        })

    def delete(self, request, id):
        user = request.user
        requested_owner_id = parse_optional_id(request.query_params.get('ownerId'))

        try:
            owner_id = resolve_owner_id(user, requested_owner_id)
        except (PermissionError, ValueError) as err:
            return Response({'success': False, 'message': str(err)}, status=status.HTTP_403_FORBIDDEN)

        folder = FileFolder.objects.filter(id=id, owner_id=owner_id).first()
        if not folder:
            return Response({'success': False, 'message': 'Folder not found.'}, status=status.HTTP_404_NOT_FOUND)

        folder.delete()
        return Response({'message': 'Folder deleted successfully.'})


class FileMoveView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        user = request.user
        requested_owner_id = parse_optional_id(request.query_params.get('ownerId'))

        try:
            owner_id = resolve_owner_id(user, requested_owner_id)
        except (PermissionError, ValueError) as err:
            return Response({'success': False, 'message': str(err)}, status=status.HTTP_403_FORBIDDEN)

        file = File.objects.filter(id=id).first()
        if not file:
            return Response({'success': False, 'message': 'File not found.'}, status=status.HTTP_404_NOT_FOUND)

        folder_id = parse_optional_id(request.data.get('folderId'))
        if folder_id:
            folder = FileFolder.objects.filter(id=folder_id, owner_id=owner_id).first()
            if not folder:
                return Response({'success': False, 'message': 'Destination folder not found.'}, status=status.HTTP_404_NOT_FOUND)

            FileFolderAssignment.objects.update_or_create(
                file=file,
                owner_id=owner_id,
                defaults={'folder': folder, 'assigned_by': user}
            )
        else:
            FileFolderAssignment.objects.filter(file=file, owner_id=owner_id).delete()

        return Response({
            'message': 'File moved to root successfully.' if folder_id is None else 'File moved to folder successfully.'
        })
