import mimetypes
import os
from uuid import uuid4
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
from flask import current_app


def get_s3_client():
    """Return a configured boto3 S3 client for Backblaze B2."""
    cfg = current_app.config
    endpoint = cfg.get("B2_ENDPOINT")
    key_id = cfg.get("B2_KEY_ID")
    application_key = cfg.get("B2_APPLICATION_KEY")
    if not all([endpoint, key_id, application_key]):
        raise RuntimeError("Backblaze B2 credentials are not fully configured.")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=application_key,
    )


def _ensure_stream(file_obj):
    stream = getattr(file_obj, "stream", None)
    if stream and hasattr(stream, "read"):
        return stream
    return file_obj


def _detect_extension(file_obj, filename_hint=None):
    candidate = filename_hint or getattr(file_obj, "filename", None) or getattr(file_obj, "name", None)
    ext = ""
    if candidate:
        ext = os.path.splitext(candidate)[1]
    if not ext:
        mimetype = getattr(file_obj, "mimetype", None)
        if mimetype:
            ext = mimetypes.guess_extension(mimetype) or ""
    return (ext or "").lower()


def save_file_to_storage(file_obj, folder, filename_hint=None):
    """Upload a file-like object to Backblaze B2 and return its public URL."""
    if not file_obj or not folder:
        return None
    cfg = current_app.config
    bucket = cfg.get("B2_BUCKET_NAME")
    public_base = (cfg.get("B2_PUBLIC_URL") or "").rstrip("/")
    if not bucket or not public_base:
        raise RuntimeError("Backblaze B2 bucket or public URL is not configured.")

    stream = _ensure_stream(file_obj)
    if hasattr(stream, "seek"):
        stream.seek(0)
    ext = _detect_extension(file_obj, filename_hint) or ""
    object_name = f"{uuid4().hex}{ext}"
    key = f"{folder.strip('/')}/{object_name}"

    extra_args = {}
    mimetype = getattr(file_obj, "mimetype", None)
    if mimetype:
        extra_args["ContentType"] = mimetype

    client = get_s3_client()
    try:
        upload_kwargs = {}
        if extra_args:
            upload_kwargs["ExtraArgs"] = extra_args
        client.upload_fileobj(stream, bucket, key, **upload_kwargs)
    except ClientError as exc:
        current_app.logger.exception("Failed to upload file to B2: %s", exc)
        raise

    return f"{public_base}/{key}"


def delete_file_from_storage(path):
    """Delete a file from Backblaze B2 using its public URL."""
    if not path:
        return False
    cfg = current_app.config
    bucket = cfg.get("B2_BUCKET_NAME")
    public_base = (cfg.get("B2_PUBLIC_URL") or "").rstrip("/")
    if not bucket or not public_base:
        return False

    key = None
    if path.startswith(public_base):
        key = path[len(public_base):].lstrip("/")
    else:
        parsed = urlparse(path)
        key = parsed.path.lstrip("/")
    if not key:
        return False

    try:
        client = get_s3_client()
        client.delete_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        current_app.logger.exception("Failed to delete file from B2")
        return False
