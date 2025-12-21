# Simple Calculator by Victor
import math


def get_number(prompt):
    """Prompt repeatedly until the user enters a valid number or 'exit'/'quit'.
    If user types 'exit' or 'quit', a SystemExit is raised to stop the program."""
    while True:
        s = input(prompt).strip()
        if s.lower() in ("exit", "quit"):
            print("Exiting calculator. Goodbye!")
            raise SystemExit
        try:
            return float(s)
        except ValueError:
            print("Invalid number. Please enter a numeric value or 'exit' to quit.")


def print_help():
    print("""
Available operations:
  Binary: +  -  *  /  %  ^ (power 'pow' or '^')  log
  Unary:  sqrt  sin  cos  tan  abs  percent  ln  log10
  Commands: history  clear  help  exit
Notes:
  - 'log' asks for value then base; both must be > 0 and base != 1.
  - 'ln' is natural logarithm; 'log10' is base-10.
Examples:
  +      (asks for two numbers)
  sqrt   (asks for one number)
  log    (asks for value then base)
""")


def main():
    history = []
    print("Simple Calculator by Victor — type 'help' to see available operations.")

    unary_ops = {
        'sqrt': lambda a: math.sqrt(a),
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'abs': abs,
        'percent': lambda a: a / 100.0,
        'ln': math.log,
        'log10': math.log10,
    }

    def safe_div(a, b):
        if b == 0:
            raise ZeroDivisionError
        return a / b

    def log_with_base(a, b):
        # Validate domain so we surface a clear ValueError for invalid inputs
        if a <= 0:
            raise ValueError("log value must be > 0")
        if b <= 0 or b == 1:
            raise ValueError("log base must be > 0 and != 1")
        return math.log(a, b)

    binary_ops = {
        '+': lambda a, b: a + b,
        '-': lambda a, b: a - b,
        '*': lambda a, b: a * b,
        '/': lambda a, b: safe_div(a, b),
        '%': lambda a, b: a % b if b != 0 else (_ for _ in ()).throw(ZeroDivisionError()),
        'pow': lambda a, b: a ** b,
        'log': lambda a, b: log_with_base(a, b),
    }

    while True:
        op = input("\nEnter operation (or 'help'): ").strip().lower()
        if op in ('exit', 'quit'):
            print("Thank you for using Victor Ilonze calculator — goodbye!")
            break
        if op == 'help':
            print_help()
            continue
        if op == 'history':
            if history:
                print("History:")
                for i, h in enumerate(history, 1):
                    print(f"  {i}. {h}")
            else:
                print("History is empty.")
            continue
        if op == 'clear':
            history.clear()
            print("History cleared.")
            continue

        # Accept '^' as 'pow'
        if op == '^':
            op = 'pow'

        try:
            if op in unary_ops:
                a = get_number("Enter number: ")
                res = unary_ops[op](a)
                expr = f"{op}({a}) = {res}"
            elif op in binary_ops:
                a = get_number("Enter first number: ")
                b = get_number("Enter second number: ")
                res = binary_ops[op](a, b)
                expr = f"{a} {op} {b} = {res}"
            else:
                print("Invalid operation, type 'help' to see available operations.")
                continue
        except ZeroDivisionError:
            res = "Error: Cannot divide by zero"
            expr = f"{a} {op} {b} = {res}"
        except ValueError as e:
            print("Math domain error:", e)
            continue
        except SystemExit:
            break
        except Exception as e:
            print("Error:", e)
            continue

        print("Result:", res)
        history.append(expr)


if __name__ == '__main__':
    main()

