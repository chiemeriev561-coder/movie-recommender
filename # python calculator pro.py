"""
Python Calculator Pro — enhanced REPL

Features:
- Safe expression evaluation (no eval): arithmetic, power, modulo
- Math functions from `math` (sin, cos, tan, log, sqrt, etc.) and complex support
- Variables and `ans` for last result
- History and `history` command
- Memory registers: `M+`, `M-`, `MR` commands
- Fraction/decimal output modes
- Unit conversion command: `convert <value> <from_unit> to <to_unit>`
- Commands: `help`, `quit`/`q`, `clear`, `vars`, `history`, `mode fraction|decimal`, `stats`
- You can enter expressions, e.g. 2*(3+sin(pi/4)) or assign: x = 5
"""

import ast
import math
import cmath
import operator as op
from fractions import Fraction
import time


# --- Safe evaluator ---
# Allowed operators map
_operators = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Pow: op.pow,
    ast.Mod: op.mod,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}

# Whitelisted names from math and cmath
_math_funcs = {k: getattr(math, k) for k in dir(math) if not k.startswith("__")}
_cmath_funcs = {k: getattr(cmath, k) for k in dir(cmath) if not k.startswith("__")}
_allowed_names = {}
_allowed_names.update(_math_funcs)
_allowed_names.update(_cmath_funcs)
_allowed_names.update({
    'pi': math.pi,
    'e': math.e,
})


def safe_eval(node, variables):
    if isinstance(node, ast.Expression):
        return safe_eval(node.body, variables)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Num):  # Python <3.8
        return node.n
    if isinstance(node, ast.BinOp):
        left = safe_eval(node.left, variables)
        right = safe_eval(node.right, variables)
        op_type = type(node.op)
        if op_type in _operators:
            return _operators[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        operand = safe_eval(node.operand, variables)
        op_type = type(node.op)
        if op_type in _operators:
            return _operators[op_type](operand)
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        if node.id in _allowed_names:
            return _allowed_names[node.id]
        raise NameError(f"Use of name '{node.id}' is not allowed")
    if isinstance(node, ast.Call):
        func = safe_eval(node.func, variables)
        args = [safe_eval(a, variables) for a in node.args]
        return func(*args)
    if isinstance(node, ast.Assign):
        # support assignment like x = expr (handled outside)
        raise SyntaxError('Assign not supported here')
    raise SyntaxError(f"Unsupported expression: {ast.dump(node)}")


# --- Units (simple offline conversions) ---
_units = {
    'length': {
        'm': 1.0,
        'km': 1000.0,
        'cm': 0.01,
        'mm': 0.001,
        'mi': 1609.344,
        'ft': 0.3048,
        'in': 0.0254,
    },
    'weight': {
        'kg': 1.0,
        'g': 0.001,
        'lb': 0.45359237,
        'oz': 0.0283495231,
    },
    'temperature': {
        # temperature handled specially
    }
}


def convert_units(value, from_u, to_u):
    from_u = from_u.lower()
    to_u = to_u.lower()
    # temperature special cases
    if from_u in ('c', 'celsius') and to_u in ('f', 'fahrenheit'):
        return value * 9/5 + 32
    if from_u in ('f', 'fahrenheit') and to_u in ('c', 'celsius'):
        return (value - 32) * 5/9
    # search categories
    for cat, table in _units.items():
        if from_u in table and to_u in table:
            return value * table[from_u] / table[to_u]
    raise ValueError('Unsupported unit conversion')


# --- REPL state ---
variables = {'ans': 0}
history = []
memory = 0.0
mode = 'decimal'  # or 'fraction'
stats = {'count': 0, 'start': time.time()}


def print_help():
    print('Commands:')
    print('  help                  Show this help')
    print('  q, quit               Exit')
    print('  history               Show input history')
    print('  vars                  Show variables')
    print('  mode fraction|decimal Switch output mode')
    print('  M+ <expr>             Add value to memory')
    print('  M- <expr>             Subtract value from memory')
    print('  MR                    Recall memory')
    print('  convert <v> <from> to <to>   Convert units')
    print('  stats                 Show session stats')
    print('You can enter expressions, e.g. 2*(3+sin(pi/4)) or assign: x = 5')


def format_result(res):
    if mode == 'fraction' and isinstance(res, (int, float)) and not isinstance(res, complex):
        try:
            return str(Fraction(res).limit_denominator())
        except Exception:
            return str(res)
    return str(res)


def handle_assignment(text):
    # split on first '='
    left, right = text.split('=', 1)
    name = left.strip()
    if not name.isidentifier():
        raise NameError('Invalid variable name')
    expr = right.strip()
    node = ast.parse(expr, mode='eval')
    val = safe_eval(node, variables)
    variables[name] = val
    variables['ans'] = val
    return val


def repl():
    global memory, mode
    print('Python Calculator Pro — type "help" for commands')
    while True:
        try:
            text = input('> ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nExiting.')
            break
        if not text:
            continue
        history.append(text)

        # commands
        tl = text.lower()
        if tl in ('q', 'quit'):
            break
        if tl == 'help':
            print_help()
            continue
        if tl == 'history':
            for i, h in enumerate(history, 1):
                print(i, h)
            continue
        if tl == 'vars':
            for k, v in variables.items():
                print(f'{k} = {v}')
            continue
        if tl.startswith('mode '):
            m = tl.split(None, 1)[1]
            if m in ('fraction', 'decimal'):
                mode = m
                print('Mode set to', mode)
            else:
                print('Unknown mode')
            continue
        if tl == 'mr':
            print(memory)
            continue
        if tl.startswith('m+'):
            expr = text[2:].strip()
            if expr:
                node = ast.parse(expr, mode='eval')
                val = safe_eval(node, variables)
                memory += val
                print('Memory =', memory)
            continue
        if tl.startswith('m-'):
            expr = text[2:].strip()
            if expr:
                node = ast.parse(expr, mode='eval')
                val = safe_eval(node, variables)
                memory -= val
                print('Memory =', memory)
            continue
        if tl.startswith('convert '):
            # convert <value> <from> to <to>
            parts = text.split()
            try:
                if len(parts) >= 4 and parts[-2].lower() == 'to':
                    value = float(parts[1])
                    from_u = parts[2]
                    to_u = parts[3]
                    res = convert_units(value, from_u, to_u)
                    print(format_result(res))
                else:
                    print('Usage: convert <value> <from_unit> to <to_unit>')
            except Exception as e:
                print('Conversion error:', e)
            continue
        if tl == 'stats':
            elapsed = time.time() - stats['start']
            print(f"Calculations: {stats['count']}  Session time: {elapsed:.1f}s")
            continue

        # assignment
        if '=' in text:
            try:
                val = handle_assignment(text)
                print('=', format_result(val))
                stats['count'] += 1
            except Exception as e:
                print('Error:', e)
            continue

        # evaluate expression
        try:
            node = ast.parse(text, mode='eval')
            val = safe_eval(node, variables)
            variables['ans'] = val
            stats['count'] += 1
            # print result
            print(format_result(val))
        except Exception as e:
            print('Error:', e)


if __name__ == '__main__':
    repl()



