"""图片接口：上传（博主）+ 读取（公开，供正文引用展示）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_admin
from app.errors import ApiError
from app.services import image_service

router = APIRouter(prefix="/api/images", tags=["images"])


@router.post("", dependencies=[Depends(get_current_admin)])
async def upload_image(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> dict[str, str]:
    return await image_service.save_image(db, file)


@router.get("/{stored_name}")
def get_image(stored_name: str) -> FileResponse:
    # 防御路径穿越：只允许纯文件名
    if "/" in stored_name or "\\" in stored_name or ".." in stored_name:
        raise ApiError(400, "bad_request", "非法文件名")
    path = settings.images_dir / stored_name
    if not path.is_file():
        raise ApiError(404, "not_found", "图片不存在")
    return FileResponse(path)
