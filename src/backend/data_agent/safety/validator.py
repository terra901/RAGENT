"""SQL 安全校验：强制只读 + 行数限制 + AST 解析 + 单语句保证。"""
from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import expressions as exp

from ..core.logging import get_logger

log = get_logger(__name__)


# 写操作关键词（在剥离字符串字面量后扫描，避免误报 SELECT 'DROP TABLE')
_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

# 危险元数据 / 维护命令
_DANGEROUS_FUNCTIONS = re.compile(
    r"\b(ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|LOAD_EXTENSION)\b",
    re.IGNORECASE,
)

# 用于剥离 SQL 里的字符串字面量 / 注释，避免关键词在字符串里被误报
_STR_LITERAL = re.compile(r"'(?:''|[^'])*'")
_DOUBLE_QUOTED = re.compile(r'"(?:""|[^"])*"')
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_literals_and_comments(sql: str) -> str:
    """执行 strip_literals_and_comments 逻辑。"""
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    sql = _STR_LITERAL.sub("''", sql)
    sql = _DOUBLE_QUOTED.sub('""', sql)
    return sql


@dataclass
class ValidationResult:
    """封装 ValidationResult 的数据结构或业务行为。"""
    is_valid: bool
    errors: list[str]
    corrected_sql: str | None = None

    @classmethod
    def ok(cls, sql: str) -> "ValidationResult":
        """执行 ok 逻辑。"""
        return cls(is_valid=True, errors=[], corrected_sql=sql)

    @classmethod
    def fail(cls, errors: list[str]) -> "ValidationResult":
        """执行 fail 逻辑。"""
        return cls(is_valid=False, errors=errors, corrected_sql=None)


class SafetyValidator:
    """SQL 安全校验器。

    校验流程:
      1. 必须能解析为恰好一条 SELECT / WITH ... SELECT 语句
      2. 剥离字符串/注释后扫描写操作关键词（兜底）
      3. AST 遍历检查写操作节点 + 危险函数
      4. 强制注入 / 收紧 LIMIT
    """

    def __init__(self, max_rows: int = 100, dialect: str | None = None):
        """初始化当前对象的依赖和内部状态。"""
        self.max_rows = max_rows
        self.dialect = dialect

    def validate(self, sql: str) -> ValidationResult:
        """校验 validate 对应的输入并返回结果。"""
        sql = (sql or "").strip().rstrip(";").strip()
        if not sql:
            return ValidationResult.fail(["SQL 为空"])

        # 1) 单语句保证
        try:
            statements = sqlglot.parse(sql, read=self.dialect)
        except Exception as e:  # noqa: BLE001
            return ValidationResult.fail([f"SQL 语法错误: {e}"])

        non_null = [s for s in statements if s is not None]
        if len(non_null) == 0:
            return ValidationResult.fail(["无法解析 SQL"])
        if len(non_null) > 1:
            return ValidationResult.fail(["仅允许单条 SELECT 语句"])

        ast = non_null[0]

        # 2) 关键词扫描（剥离字符串字面量后）
        stripped = _strip_literals_and_comments(sql)
        errors: list[str] = []
        if _WRITE_KEYWORDS.search(stripped):
            errors.append("检测到写操作关键词，仅允许只读查询")
        if _DANGEROUS_FUNCTIONS.search(stripped):
            errors.append("检测到危险函数 / 维护命令")
        if errors:
            return ValidationResult.fail(errors)

        # 3) AST 节点级检查
        ast_errors = self._check_ast(ast)
        if ast_errors:
            return ValidationResult.fail(ast_errors)

        # 4) 顶层必须是 SELECT 或 WITH ... SELECT
        if not self._is_pure_select(ast):
            return ValidationResult.fail(["顶层语句必须是 SELECT"])

        # 5) 强制 LIMIT
        corrected = self._ensure_limit(ast)
        return ValidationResult.ok(corrected)

    def _check_ast(self, ast: exp.Expression) -> list[str]:
        """校验 check_ast 对应的输入并返回结果。"""
        errors: list[str] = []
        write_node_types = (
            exp.Insert, exp.Update, exp.Delete,
            exp.Drop, exp.Create, exp.Alter,
            exp.TruncateTable, exp.Merge, exp.Command,
            exp.Grant, exp.Revoke,
        )
        dangerous_funcs = {"ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX", "LOAD_EXTENSION"}

        for node in ast.walk():
            if isinstance(node, write_node_types):
                errors.append(f"AST 检测到写操作: {type(node).__name__}")
            if isinstance(node, exp.Anonymous) and node.name.upper() in dangerous_funcs:
                errors.append(f"AST 检测到危险函数: {node.name}")
        return errors

    @staticmethod
    def _is_pure_select(ast: exp.Expression) -> bool:
        """执行 is_pure_select 逻辑。"""
        if isinstance(ast, exp.Select):
            return True
        if isinstance(ast, exp.Union):
            return True
        if isinstance(ast, exp.With) and isinstance(ast.this, (exp.Select, exp.Union)):
            return True
        # 顶层是 SELECT 包在表达式里也算
        select = ast.find(exp.Select)
        return select is not None and isinstance(ast, (exp.Select, exp.Union, exp.With))

    def _ensure_limit(self, ast: exp.Expression) -> str:
        """确保最外层 SELECT 有 LIMIT，且 LIMIT <= max_rows。"""
        # 找最外层的 Select（CTE 会包一层 With）
        outer = ast
        if isinstance(ast, exp.With):
            outer = ast.this
        if isinstance(outer, exp.Union):
            # UNION 在外层 set 上加 LIMIT
            select_holder = outer
        else:
            select_holder = ast.find(exp.Select) or ast

        existing_limit = select_holder.args.get("limit") if hasattr(select_holder, "args") else None
        if existing_limit is None and isinstance(select_holder, exp.Select):
            existing_limit = select_holder.find(exp.Limit)

        if isinstance(existing_limit, exp.Limit):
            existing_val = self._read_limit_value(existing_limit)
            # 表达式 / placeholder / 解析失败 → 强制替换
            if existing_val is None or existing_val > self.max_rows:
                existing_limit.set("expression", exp.Literal.number(self.max_rows))
        else:
            # 没有 LIMIT，追加
            if hasattr(select_holder, "set"):
                select_holder.set(
                    "limit",
                    exp.Limit(expression=exp.Literal.number(self.max_rows)),
                )

        return ast.sql(dialect=self.dialect)

    @staticmethod
    def _read_limit_value(limit_node: exp.Limit) -> int | None:
        """从 Limit 节点取数值，无法识别时返回 None。"""
        target = limit_node.expression
        if target is None:
            return None
        if isinstance(target, exp.Literal):
            try:
                return int(target.this)
            except (TypeError, ValueError):
                return None
        # 表达式 / placeholder / 子查询 → 不安全，按 None 处理
        return None
