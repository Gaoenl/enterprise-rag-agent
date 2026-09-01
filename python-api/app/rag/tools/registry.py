"""工具注册表：工具名 → 执行函数。

执行函数签名：func(tool_input: dict) -> str（返回文本结果）。
工具执行失败由函数返回错误文本或抛异常，由调用方决定降级方式。
"""
from typing import Callable,Any
import ast
import operator
import re
# 工具执行函数：dict 入参 -> 文本结果
ToolFunc= Callable[[dict[str:Any]], str]
_REGISTRY: dict[str, ToolFunc] = {}
def register(name: str, func: ToolFunc) -> None:
    """注册工具。"""
    _REGISTRY[name] = func


def is_registered(name: str) -> bool:
    """工具是否已注册。"""
    return name in _REGISTRY

def execute(name: str, tool_input: dict[str, Any]) -> str:
    """执行工具并返回文本结果。"""
    func = _REGISTRY.get(name)
    if func is None:
        raise KeyError(f"工具未注册: {name}")
    return func(tool_input)
# ── 内置工具：安全计算器 ──────────────────────────────
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
def _calculator(tool_input: dict[str, Any]) -> str:
    """安全计算器：仅支持数字、四则运算、取模与幂，禁止任意代码执行。"""
    expression = str(tool_input.get("expression") or "").strip()
    if not expression:
        return "错误：缺少 expression 参数。"

    # 字符白名单校验。
    if not re.fullmatch(r"[0-9+\-*/().\s%]*", expression):
        return "错误：表达式包含不支持的字符。"

    def eval_node(node):
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("仅支持数值常量")
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
            left = eval_node(node.left)
            right = eval_node(node.right)
            return _ALLOWED_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(node.op)](eval_node(node.operand))
        raise ValueError("不支持的表达式")

    try:
        result = eval_node(ast.parse(expression, mode="eval"))
        return f"计算结果：{result}"
    except Exception as exc:
        return f"计算失败：{exc}"
register("calculator", _calculator)