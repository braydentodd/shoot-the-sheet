"""
The Glass - Math Evaluator

Restricted AST-based evaluator for runtime mathematical string expressions.
Only whitelisted arithmetic nodes are permitted; any attempt to access
attributes, call functions, or use disallowed syntax raises TypeError.
"""

import ast
import operator
from typing import Dict

_AST_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def evaluate(expr: str, variables: Dict[str, float]) -> float:
    """Safely evaluate a mathematical expression using AST parsing.

    Only allows basic arithmetic operations and variable lookups.
    Raises ``TypeError`` or ``NameError`` on any disallowed construct.
    """
    node = ast.parse(expr, mode='eval')

    def _eval(node_to_eval):
        if isinstance(node_to_eval, ast.Expression):
            return _eval(node_to_eval.body)
        if isinstance(node_to_eval, ast.Constant):
            if isinstance(node_to_eval.value, (int, float)):
                return node_to_eval.value
            raise TypeError(
                f"Unsupported constant type in math expression: {type(node_to_eval.value)}"
            )
        if isinstance(node_to_eval, ast.Num):  # for python < 3.8
            return node_to_eval.n
        if isinstance(node_to_eval, ast.Name):
            if node_to_eval.id in variables:
                return variables[node_to_eval.id]
            raise NameError(f"Undefined variable in math expression: {node_to_eval.id}")
        if isinstance(node_to_eval, ast.BinOp):
            op_type = type(node_to_eval.op)
            if op_type in _AST_OPERATORS:
                return _AST_OPERATORS[op_type](
                    _eval(node_to_eval.left), _eval(node_to_eval.right)
                )
            raise TypeError(f"Unsupported binary operator: {op_type}")
        if isinstance(node_to_eval, ast.UnaryOp):
            op_type = type(node_to_eval.op)
            if op_type in _AST_OPERATORS:
                return _AST_OPERATORS[op_type](_eval(node_to_eval.operand))
            raise TypeError(f"Unsupported unary operator: {op_type}")
        raise TypeError(
            f"Unsupported AST node type in math expression: {type(node_to_eval)}"
        )

    return _eval(node)
