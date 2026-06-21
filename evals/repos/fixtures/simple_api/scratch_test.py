import ast
import re
from typing import Optional, Tuple

def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()

def fuzzy_find_in_text(search_text: str, content: str) -> Optional[str]:
    parts = search_text.split()
    if not parts:
        return None
    escaped_parts = [re.escape(p) for p in parts]
    regex = r'\s+'.join(escaped_parts)
    # allow leading/trailing space flexibly
    match = re.search(regex, content)
    if match:
        return match.group(0)
    return None

def find_symbol_bounds(content: str, symbol_name: str) -> Optional[Tuple[int, int]]:
    class Finder(ast.NodeVisitor):
        def __init__(self):
            self.bounds = None
        def visit_FunctionDef(self, node):
            if node.name == symbol_name and not self.bounds:
                self.bounds = (node.lineno, node.end_lineno)
            self.generic_visit(node)
        def visit_AsyncFunctionDef(self, node):
            if node.name == symbol_name and not self.bounds:
                self.bounds = (node.lineno, node.end_lineno)
            self.generic_visit(node)
        def visit_ClassDef(self, node):
            if node.name == symbol_name and not self.bounds:
                self.bounds = (node.lineno, node.end_lineno)
            self.generic_visit(node)
            
    try:
        tree = ast.parse(content)
        finder = Finder()
        finder.visit(tree)
        return finder.bounds
    except SyntaxError:
        return None

def apply_fuzzy_patch(search_text: str, replace_text: str, content: str) -> str:
    # 1. Exact match
    if search_text in content:
        print("exact match")
        return content.replace(search_text, replace_text, 1)
        
    # 2. Whitespace match
    matched = fuzzy_find_in_text(search_text, content)
    if matched:
        print("whitespace match")
        return content.replace(matched, replace_text, 1)
        
    # 3. Symbol match
    m = re.search(r'^(?:async\s+)?(?:def|class)\s+([a-zA-Z_]\w*)\b', search_text.strip())
    if m:
        symbol_name = m.group(1)
        bounds = find_symbol_bounds(content, symbol_name)
        if bounds:
            start_idx, end_idx = bounds
            print(f"symbol match: {symbol_name} at lines {start_idx}-{end_idx}")
            lines = content.splitlines(keepends=True)
            # Remove decorators if they exist? ast node.lineno includes decorators!
            # Wait, no, node.lineno for decorators is the first decorator, but in some Python versions it's the `def`. 
            # In Python 3.8+, node.lineno is the `def` line if no decorators, but it starts at decorators if present.
            # Let's replace those lines.
            prefix = "".join(lines[:start_idx-1])
            suffix = "".join(lines[end_idx:]) if end_idx else ""
            return prefix + replace_text + "\n" + suffix
            
    raise Exception("PatchError")

content = '''def divide(a: float, b: float) -> float:
    """Return a divided by b."""
    if b == 0:
        raise ValueError("Divisor cannot be zero")
    return a / b
'''

search = '''def divide(a, b):
    try:
        return a / b
'''

replace = '''def divide(a, b):
    try:
        return a / b
    except ZeroDivisionError as e:
        raise ZeroDivisionError("Cannot divide by zero") from e
'''

print(apply_fuzzy_patch(search, replace, content))
