import os
import boto3
from django.conf import settings


def get_s3_client():
    kwargs = {
        'region_name': settings.AWS_REGION or 'ap-south-1',
    }
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs['aws_access_key_id'] = settings.AWS_ACCESS_KEY_ID
        kwargs['aws_secret_access_key'] = settings.AWS_SECRET_ACCESS_KEY

    return boto3.client('s3', **kwargs)


def s3_upload(key: str, body: bytes, content_type: str):
    s3 = get_s3_client()
    s3.put_object(
        Bucket=settings.AWS_S3_BUCKET_NAME,
        Key=key,
        Body=body,
        ContentType=content_type
    )


def s3_delete(key: str):
    s3 = get_s3_client()
    try:
        s3.delete_object(
            Bucket=settings.AWS_S3_BUCKET_NAME,
            Key=key
        )
    except Exception as e:
        print(f"S3 delete error: {e}")


def s3_get_download_url(key: str, original_name: str, expires_in: int = 60) -> str:
    s3 = get_s3_client()
    safe_name = original_name.replace('\r', '_').replace('\n', '_').replace('"', '_').replace('\\', '_')[:255]
    return s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': settings.AWS_S3_BUCKET_NAME,
            'Key': key,
            'ResponseContentDisposition': f'attachment; filename="{safe_name}"'
        },
        ExpiresIn=expires_in
    )


def s3_get_view_url(key: str, original_name: str, mime_type: str, expires_in: int = 60) -> str:
    s3 = get_s3_client()
    safe_name = original_name.replace('\r', '_').replace('\n', '_').replace('"', '_').replace('\\', '_')[:255]
    return s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': settings.AWS_S3_BUCKET_NAME,
            'Key': key,
            'ResponseContentType': mime_type or 'application/octet-stream',
            'ResponseContentDisposition': f'inline; filename="{safe_name}"'
        },
        ExpiresIn=expires_in
    )
