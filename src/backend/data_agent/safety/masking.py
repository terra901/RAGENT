"""敏感数据脱敏 / 列级保护。

三种模式（DA_MASKING_MODE）:
- off    : 不做任何处理（默认）
- mask   : 在结果返回阶段对敏感列做后置脱敏（13*****1234 等）
- reject : 检测 SQL 是否查询敏感列；命中即拒绝执行

敏感列配置在 semantic_layer.json 的 sensitive_columns 块：
    {"users.phone": "phone", "users.id_card": "id_card", "*.email": "email"}

列名前缀 "*" 表示匹配任意表的同名列；普通 "table.column" 精确匹配。

支持的脱敏类型见 _MASKERS，未匹配时走 _mask_default。
"""
from __future__ import annotations

import re
from typing import Any

from ..core.logging import get_logger

log = get_logger(__name__)


# 列名扫描专用：只剥离单引号字符串和注释，保留双引号 / 反引号包裹的标识符
_SINGLE_QUOTED = re.compile(r"'(?:''|[^'])*'")
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_for_column_scan(sql: str) -> str:
    """执行 strip_for_column_scan 逻辑。"""
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    sql = _SINGLE_QUOTED.sub("''", sql)
    return sql


# ---------- 单值脱敏 ----------

def _mask_phone(v: Any) -> str:
    """执行 mask_phone 逻辑。"""
    s = str(v)
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11:
        return digits[:3] + "****" + digits[7:]
    if len(digits) >= 8:
        return digits[:3] + "*" * (len(digits) - 6) + digits[-3:]
    return "*" * len(digits) if digits else "***"


def _mask_id_card(v: Any) -> str:
    """执行 mask_id_card 逻辑。"""
    s = str(v).strip()
    if len(s) == 18:
        return s[:6] + "********" + s[-4:]
    if len(s) == 15:
        return s[:6] + "******" + s[-3:]
    if len(s) >= 6:
        return s[:3] + "*" * (len(s) - 6) + s[-3:]
    return "*" * len(s) if s else "***"


def _mask_email(v: Any) -> str:
    """执行 mask_email 逻辑。"""
    s = str(v)
    if "@" not in s:
        return _mask_default(s)
    local, domain = s.split("@", 1)
    masked_local = "*" if len(local) <= 1 else local[0] + "*" * (len(local) - 1)
    return masked_local + "@" + domain


def _mask_name(v: Any) -> str:
    """执行 mask_name 逻辑。"""
    s = str(v)
    if not s:
        return ""
    if len(s) <= 1:
        return "*"
    return s[0] + "*" * (len(s) - 1)


def _mask_bank_card(v: Any) -> str:
    """执行 mask_bank_card 逻辑。"""
    s = str(v)
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        return "*" * (len(digits) - 4) + digits[-4:]
    return "*" * len(digits) if digits else "***"


def _mask_address(v: Any) -> str:
    """执行 mask_address 逻辑。"""
    s = str(v)
    if len(s) <= 6:
        return (s[:2] if s else "") + "***"
    return s[:6] + "***"


def _mask_ip(v: Any) -> str:
    """执行 mask_ip 逻辑。"""
    s = str(v)
    parts = s.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.***.***.{parts[3]}"
    return _mask_default(s)


def _mask_default(v: Any) -> str:
    """执行 mask_default 逻辑。"""
    s = str(v)
    if not s:
        return ""
    if len(s) <= 2:
        return "*" * len(s)
    return s[0] + "*" * (len(s) - 2) + s[-1]


_MASKERS = {
    "phone": _mask_phone,
    "id_card": _mask_id_card,
    "email": _mask_email,
    "name": _mask_name,
    "bank_card": _mask_bank_card,
    "address": _mask_address,
    "ip": _mask_ip,
    "default": _mask_default,
}


def supported_mask_types() -> list[str]:
    """执行 supported_mask_types 逻辑。"""
    return list(_MASKERS.keys())


# ---------- Masker ----------

class Masker:
    """脱敏器：基于 sensitive_columns 配置对结果列做脱敏 / SQL 拒绝。

    sensitive_columns 形如 {"users.phone": "phone", "*.email": "email"}：
      - "table.col" 精确匹配
      - "*.col" 或仅 "col"：匹配任意表的同名列
    """

    def __init__(
        self,
        sensitive_columns: dict[str, str] | None = None,
        mode: str = "off",
    ):
        """初始化当前对象的依赖和内部状态。"""
        self.mode = mode if mode in ("off", "mask", "reject") else "off"
        self._by_full: dict[str, str] = {}        # 显式 "table.column" (lowercase) → type
        self._by_col_only: dict[str, str] = {}    # 显式 "*.column" 或 "column" → type
        # 从 _by_full 派生的兜底列名映射，仅用于结果脱敏（SQL 扫描忽略，避免重复命中）
        self._fallback_col: dict[str, str] = {}

        for raw_key, mtype in (sensitive_columns or {}).items():
            k = raw_key.strip().lower()
            if not k:
                continue
            mtype = mtype.strip().lower()
            if mtype not in _MASKERS:
                log.warning("未知敏感列类型 %r，回退为 default", mtype)
                mtype = "default"

            if "." in k:
                tbl, col = k.split(".", 1)
                tbl = tbl.strip()
                col = col.strip()
                if tbl in ("", "*"):
                    self._by_col_only[col] = mtype
                else:
                    self._by_full[f"{tbl}.{col}"] = mtype
                    self._fallback_col.setdefault(col, mtype)
            else:
                self._by_col_only[k] = mtype

    @property
    def enabled(self) -> bool:
        """执行 enabled 逻辑。"""
        return self.mode != "off" and bool(
            self._by_full or self._by_col_only or self._fallback_col
        )

    @property
    def configured_columns(self) -> list[str]:
        """所有已配置的列（"table.column" 或 "*.column"），主要供调试 / schema 标注。"""
        out = list(self._by_full.keys())
        for col in self._by_col_only:
            # 避免与 _by_full 重复展示
            if not any(full.endswith("." + col) for full in self._by_full):
                out.append(f"*.{col}")
        return sorted(out)

    # ----- 结果行脱敏（mask 模式） -----

    def detect_columns(
        self, columns: list[str], table_hint: str | None = None
    ) -> dict[int, str]:
        """返回 {col_index: mask_type}。

        匹配优先级：
          1. (table_hint, column) → _by_full
          2. column → _by_col_only（显式 "*.column" / "column"）
          3. column → _fallback_col（从 "table.column" 配置派生的兜底）
        """
        out: dict[int, str] = {}
        for idx, col in enumerate(columns):
            col_low = (col or "").lower()
            mt: str | None = None
            if table_hint:
                mt = self._by_full.get(f"{table_hint.lower()}.{col_low}")
            if mt is None:
                mt = self._by_col_only.get(col_low)
            if mt is None:
                mt = self._fallback_col.get(col_low)
            if mt is not None:
                out[idx] = mt
        return out

    def apply_to_rows(
        self,
        columns: list[str],
        rows: list[list[Any]] | list[tuple[Any, ...]],
        table_hint: str | None = None,
    ) -> tuple[list[list[Any]], list[str]]:
        """对 rows 中的敏感列做脱敏，返回 (new_rows, masked_column_names)。

        - mode=off 时透明返回（不复制）
        - 否则始终复制为 list 以避免外部 mutation
        """
        if self.mode != "mask" or not self.enabled:
            return list(rows) if not isinstance(rows, list) else rows, []

        idx_map = self.detect_columns(columns, table_hint=table_hint)
        if not idx_map:
            return list(rows), []

        masked_cols = [columns[i] for i in sorted(idx_map.keys())]
        new_rows: list[list[Any]] = []
        for row in rows:
            row_list = list(row)
            for idx, mt in idx_map.items():
                if idx < len(row_list) and row_list[idx] is not None:
                    fn = _MASKERS.get(mt, _mask_default)
                    try:
                        row_list[idx] = fn(row_list[idx])
                    except Exception as e:  # noqa: BLE001
                        log.debug("脱敏 %s 失败（保留原值）: %s", mt, e)
            new_rows.append(row_list)
        return new_rows, masked_cols

    # ----- SQL 检测（reject 模式） -----

    def find_sensitive_in_sql(self, sql: str) -> list[str]:
        """剥离单引号字符串 / 注释后扫描 SQL 是否引用了敏感列。

        注意：保留双引号 / 反引号包裹的标识符（Postgres / MySQL 中是合法标识符）。
        返回命中的列标识列表（"table.column" 或 "column"），空表示未命中。
        仅扫描 _by_full + _by_col_only（显式配置），不扫描 _fallback_col 派生项，
        避免 "users.phone" 配置同时命中 "users.phone" 与 "phone" 两个 key。
        """
        if not sql or not self.enabled:
            return []
        cleaned = _strip_for_column_scan(sql)
        hits: set[str] = set()

        # 1) 精确 table.column（含 t.col / "t"."col" / `t`.`col`）
        for full in self._by_full:
            tbl, col = full.split(".", 1)
            pat = re.compile(
                rf"""(?ix)
                ["`]?{re.escape(tbl)}["`]?
                \s*\.\s*
                ["`]?{re.escape(col)}["`]?
                """
            )
            if pat.search(cleaned):
                hits.add(full)

        # 2) 仅列名（显式 "*.column" / "column"）
        for col in self._by_col_only:
            pat = re.compile(rf"(?i)(?<![\w]){re.escape(col)}(?![\w])")
            if pat.search(cleaned):
                hits.add(col)

        return sorted(hits)

    def check_sql_or_raise(self, sql: str) -> list[str]:
        """reject 模式下：检测 SQL 是否命中敏感列，命中即返回列表（调用方决定 emit error）。

        mode != "reject" 或未启用时始终返回空。
        """
        if self.mode != "reject" or not self.enabled:
            return []
        return self.find_sensitive_in_sql(sql)
