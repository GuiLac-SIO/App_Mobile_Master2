import os
from typing import Optional

import boto3


def get_s3_client():
    endpoint = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def get_bucket_name() -> str:
    return os.getenv("MINIO_BUCKET", "photos")


def ensure_bucket(client=None, bucket: Optional[str] = None) -> None:
    if client is None:
        client = get_s3_client()
    if bucket is None:
        bucket = get_bucket_name()
    existing = client.list_buckets().get("Buckets", [])
    if not any(b["Name"] == bucket for b in existing):
        client.create_bucket(Bucket=bucket)


def put_object(*, object_name: str, data: bytes, content_type: str, client=None, bucket: Optional[str] = None):
    if client is None:
        client = get_s3_client()
    if bucket is None:
        bucket = get_bucket_name()
    client.put_object(Bucket=bucket, Key=object_name, Body=data, ContentType=content_type)


def get_object_bytes(*, object_name: str, client=None, bucket: Optional[str] = None) -> bytes:
    if client is None:
        client = get_s3_client()
    if bucket is None:
        bucket = get_bucket_name()
    resp = client.get_object(Bucket=bucket, Key=object_name)
    return resp["Body"].read()
