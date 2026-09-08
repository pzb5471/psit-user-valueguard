"""M1-09 ZIP 输出：确定性标准 ZIP 与清单/校验和序列化（技术实施规格 5.4）。

- JSON 全部使用 ensure_ascii=False、indent=2、sort_keys=True，保证两次构建字节一致；
- ZIP 条目按相对路径升序写入，条目时间戳固定为 2024-01-01、权限 0644、
  ZIP_DEFLATED、不写目录条目（与 tests/m1/importing/zip_fixtures.py 的 make_zip
  保持一致），从而得到可复现的字节流；
- checksums.json 键集合恰好覆盖 manifest.json、全部案例文件与全部图片文件，
  不含自身；调用方传入的条目字典已经按此构造。
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping

_ZIP_DATE_TIME = (2024, 1, 1, 0, 0, 0)


def json_bytes(payload: object) -> bytes:
    """确定性 JSON 字节：ensure_ascii=False、indent=2、键排序。"""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode(
        "utf-8"
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_checksums(entries: Mapping[str, bytes]) -> dict[str, str]:
    """按实际写入字节计算除自身体外的全部条目 SHA-256。"""
    return {
        name: sha256_bytes(data)
        for name, data in sorted(entries.items())
        if name != "checksums.json"
    }


def write_standard_zip(entries: Mapping[str, bytes]) -> bytes:
    """按排序条目名写入确定性标准 ZIP，返回字节流。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644) << 16
            zf.writestr(info, entries[name])
    return buffer.getvalue()
