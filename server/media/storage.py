"""本地媒体落盘。"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,63}$")
SAFE_EXT_RE = re.compile(r"^\.[A-Za-z0-9]{1,16}$")


def normalize_prefix(raw: str | None) -> str:
    text = (raw or "file").strip().strip("/")
    if not text:
        text = "file"
    if ".." in text or not PREFIX_RE.match(text):
        raise ValueError("prefix 不合法")
    return text


def file_ext(filename: str | None) -> str:
    name = (filename or "").strip()
    if "." not in name:
        raise ValueError("文件名须包含扩展名")
    ext = "." + name.rsplit(".", 1)[-1].lower()
    if not SAFE_EXT_RE.match(ext):
        raise ValueError("扩展名不合法")
    return ext


def build_relative_path(*, product: str, user_id: int | str, prefix: str, filename: str | None) -> str:
    ext = file_ext(filename)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    stem = f"{uuid.uuid4().hex}{ext}"
    return f"{product}/{user_id}/{prefix}/{day}/{stem}"


def save_bytes(media_dir: Path, relative: str, data: bytes) -> Path:
    if ".." in relative or relative.startswith(("/", "\\")):
        raise ValueError("路径不合法")
    root = media_dir.resolve()
    dest = (media_dir / relative).resolve()
    try:
        dest.relative_to(root)
    except ValueError as exc:
        raise ValueError("路径越界") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def public_url(base: str, relative: str) -> str:
    root = (base or "").strip().rstrip("/")
    path = relative.lstrip("/")
    if not root:
        return f"/media/{path}"
    return f"{root}/media/{path}"


def relative_from_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise ValueError("缺少 url")
    marker = "/media/"
    idx = text.find(marker)
    if idx < 0:
        raise ValueError("不是平台媒体地址")
    rel = text[idx + len(marker) :].split("?", 1)[0].split("#", 1)[0].lstrip("/")
    if not rel or ".." in rel:
        raise ValueError("媒体路径不合法")
    return rel


def resolve_relative(*, path: str | None = None, url: str | None = None) -> str:
    raw_path = (path or "").strip().lstrip("/")
    if raw_path:
        if ".." in raw_path or raw_path.startswith(("\\",)):
            raise ValueError("路径不合法")
        return raw_path
    return relative_from_url(url or "")


def assert_owned_by_user(relative: str, *, user_id: str, product: str | None = None) -> None:
    parts = relative.split("/")
    if len(parts) < 2:
        raise PermissionError("路径不完整")
    if product and parts[0] != product:
        raise PermissionError("产品不匹配")
    if parts[1] != str(user_id):
        raise PermissionError("无权删除该文件")


def assert_under_product(relative: str, product: str) -> None:
    prefix = f"{product}/"
    if not relative.startswith(prefix):
        raise PermissionError("产品前缀不匹配")


def keep_keys_from_urls(urls: list | tuple | set | None) -> set[str]:
    keys: set[str] = set()
    for raw in urls or []:
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            keys.add(relative_from_url(text))
        except ValueError:
            # 已是相对键
            rel = text.lstrip("/")
            if rel and ".." not in rel:
                keys.add(rel)
    return keys


def iter_product_prefix_files(media_dir: Path, *, product: str, prefix: str):
    """
    产出 (relative, path) ，相对键形如 product/user_id/prefix/...
    """
    root = media_dir.resolve()
    base = (media_dir / product).resolve()
    try:
        base.relative_to(root)
    except ValueError as exc:
        raise ValueError("产品目录越界") from exc
    if not base.is_dir():
        return
    prefix_norm = (prefix or "file").strip().strip("/")
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        parts = rel.split("/")
        # product / user_id / prefix / ...
        if len(parts) < 4 or parts[0] != product or parts[2] != prefix_norm:
            continue
        yield rel, path


def gc_orphans(
    media_dir: Path,
    *,
    product: str,
    prefix: str,
    keep_urls: list | None,
    min_age_hours: int,
) -> dict:
    import time

    age = max(1, int(min_age_hours))
    cutoff = time.time() - age * 3600
    keep = keep_keys_from_urls(keep_urls)
    scanned = 0
    deleted = 0
    skipped_young = 0
    skipped_keep = 0
    for rel, path in iter_product_prefix_files(media_dir, product=product, prefix=prefix):
        scanned += 1
        if rel in keep:
            skipped_keep += 1
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > cutoff:
            skipped_young += 1
            continue
        try:
            if delete_bytes(media_dir, rel):
                deleted += 1
        except (ValueError, OSError):
            continue
    return {
        "ok": True,
        "scanned": scanned,
        "deleted": deleted,
        "skipped_young": skipped_young,
        "skipped_keep": skipped_keep,
    }


def delete_bytes(media_dir: Path, relative: str) -> bool:
    """删除文件；不存在返回 False。"""
    if ".." in relative or relative.startswith(("/", "\\")):
        raise ValueError("路径不合法")
    root = media_dir.resolve()
    dest = (media_dir / relative).resolve()
    try:
        dest.relative_to(root)
    except ValueError as exc:
        raise ValueError("路径越界") from exc
    if not dest.is_file():
        return False
    dest.unlink()
    # 尝试清理空目录（最多向上两级，忽略失败）
    parent = dest.parent
    for _ in range(3):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
        try:
            parent.relative_to(root)
        except ValueError:
            break
    return True
