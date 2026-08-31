"""图片上传（FR-POST-05、NFR-SEC-03、D2）。

- 校验格式与大小，杜绝恶意文件（NFR-SEC-03）。
- 存储名用 uuid 生成，不用原始文件名（D2：中文/空格/路径穿越风险）。
- 上传时 post_id 为 NULL，文章保存时由 post_service 关联正文引用的图片。
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import ApiError
from app.models import Image

_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp"}


async def save_image(db: Session, file: UploadFile) -> dict[str, str]:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise ApiError(400, "bad_format", "仅支持 png / jpg / jpeg / gif / webp / svg 等图片格式")

    data = await file.read()
    if not data:
        raise ApiError(400, "empty_file", "图片内容为空")
    if len(data) > settings.upload_max_mb * 1024 * 1024:
        raise ApiError(413, "too_large", f"图片大小不能超过 {settings.upload_max_mb} MB")

    stored_name = uuid.uuid4().hex + ext  # 系统生成唯一名，不用原始文件名
    images_dir = settings.images_dir
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / stored_name).write_bytes(data)

    image = Image(stored_name=stored_name, post_id=None, file_size=len(data))
    db.add(image)
    db.commit()
    db.refresh(image)
    return {"url": f"/api/images/{stored_name}"}
