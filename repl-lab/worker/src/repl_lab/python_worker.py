"""Persistent Python computation worker. Run ONLY in the verified container.

The import/builtin restrictions are defense in depth, not a Python sandbox.
Docker, no host mounts/secrets/network, and resource limits are the boundary.
AST, compile, exec, higher-order functions, classes, and generated modules work.
"""
import ast
import builtins
import contextlib
import io
import json
import sys
import math

MODULES = {"ast", "collections", "functools", "itertools", "operator", "math",
           "statistics", "heapq", "bisect", "re", "json", "types", "copy"}
MAX_BYTES = 65536


def approved_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".")[0] not in MODULES:
        raise ImportError("Module is outside the computation capability set")
    return builtins.__import__(name, globals, locals, fromlist, level)


class Output(io.TextIOBase):
    def __init__(self):
        self.parts, self.size = [], 0

    def write(self, text):
        self.size += len(text.encode())
        if self.size > 8192:
            raise ValueError("Printed output limit")
        self.parts.append(text)
        return len(text)


def namespace():
    allowed = {k: v for k, v in vars(builtins).items()
               if k not in {"open", "input", "breakpoint", "help", "exit", "quit", "__import__"}}
    allowed["__import__"] = approved_import
    return {"__builtins__": allowed, "__name__": "generated"}


def ast_data(value):
    if isinstance(value, ast.AST):
        return {"node": type(value).__name__, "fields": {k: ast_data(v) for k, v in ast.iter_fields(value)}}
    if isinstance(value, list):
        return [ast_data(v) for v in value]
    if isinstance(value, bytes):
        return {"literal": "bytes", "hex": value.hex()}
    if isinstance(value, complex):
        return {"literal": "complex", "real": value.real, "imag": value.imag}
    if value is Ellipsis:
        return {"literal": "ellipsis"}
    if value is None or type(value) in (str, int, bool) or (type(value) is float and math.isfinite(value)):
        return value
    raise ValueError("Unsupported AST value")


def ast_from_data(value, depth=0):
    if depth > 80:
        raise ValueError("AST depth limit")
    if isinstance(value, list):
        return [ast_from_data(v, depth + 1) for v in value]
    if isinstance(value, dict):
        if set(value) == {"literal", "hex"} and value["literal"] == "bytes":
            return bytes.fromhex(value["hex"])
        if set(value) == {"literal", "real", "imag"} and value["literal"] == "complex":
            return complex(value["real"], value["imag"])
        if value == {"literal": "ellipsis"}:
            return Ellipsis
        if set(value) != {"node", "fields"} or not isinstance(value["node"], str):
            raise ValueError("Invalid AST node")
        cls = getattr(ast, value["node"], None)
        if not isinstance(cls, type) or not issubclass(cls, ast.AST) or not isinstance(value["fields"], dict):
            raise ValueError("Unknown AST node")
        if set(value["fields"]) != set(cls._fields):
            raise ValueError("AST fields mismatch")
        return cls(**{k: ast_from_data(v, depth + 1) for k, v in value["fields"].items()})
    if value is None or type(value) in (str, int, bool) or (type(value) is float and math.isfinite(value)):
        return value
    raise ValueError("Invalid AST field")


def structure(request):
    """Syntax only. Never evaluate candidates or run module-level statements here."""
    operation = request.get("operation")
    if operation == "parse" and set(request) == {"operation", "source"}:
        tree = ast.parse(request["source"], filename="<artifact>", mode="exec")
        compile(tree, "<artifact>", "exec")
        return {"value": ast_data(tree)}
    if operation == "render" and set(request) == {"operation", "forms"}:
        tree = ast.fix_missing_locations(ast_from_data(request["forms"]))
        if not isinstance(tree, ast.Module):
            raise ValueError("Artifact must be a module")
        compile(tree, "<artifact>", "exec")
        source = ast.unparse(tree)
        if ast_data(ast.parse(source)) != request["forms"]:
            raise ValueError("Rendered source changes the supplied AST")
        return {"value": source}
    raise ValueError("Invalid structural operation")


def evaluate(request, scope):
    if set(request) != {"source", "bindings"} or not isinstance(request["source"], str):
        raise ValueError("Expected source and bindings")
    bindings = request["bindings"]
    if not isinstance(bindings, dict) or any(not k.isidentifier() or k.startswith("_") for k in bindings):
        raise ValueError("Invalid binding name")
    tree = ast.parse(request["source"], filename="<agent-cell>", mode="exec")
    scope.update(bindings)
    tail = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
    output = Output()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        exec(compile(tree, "<agent-cell>", "exec"), scope)
        value = eval(compile(ast.Expression(tail.value), "<agent-cell>", "eval"), scope) if tail else None
    # No repr, pickle, or arbitrary object serialization on the trusted side.
    return {"value": value, "printed": "".join(output.parts)}


def main():
    scope = namespace()
    while True:
        raw = sys.stdin.buffer.readline(MAX_BYTES + 1)
        if not raw:
            return
        if len(raw) > MAX_BYTES or not raw.endswith(b"\n"):
            raise ValueError("Input limit or incomplete request")
        try:
            request = json.loads(raw)
            response = structure(request) if "operation" in request else evaluate(request, scope)
            wire = json.dumps(response, allow_nan=False, separators=(",", ":"))
            if len(wire.encode()) >= MAX_BYTES:
                raise ValueError("Result limit")
        except BaseException as error:
            wire = json.dumps({"error": type(error).__name__ + ": " + str(error)[:1000]})
        sys.stdout.write(wire + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
