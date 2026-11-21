"""Resolve literal dynamic import targets using statically known loader bindings."""

import ast
import importlib.util
from contextlib import contextmanager

IMPORT_LOADERS = {"importlib": "import_module", "builtins": "__import__"}


class ImportScope:
    def __init__(self, parent=None, kind="module"):
        self.parent = parent
        self.kind = kind
        self.module = parent.module if parent else self
        self.bindings = {}
        self.globals = set()

    def bind(self, name, value=None):
        if self.bindings.setdefault(name, value) != value:
            self.bindings[name] = None

    def resolve(self, name):
        if name in self.bindings:
            return self.bindings[name]
        if self.parent is None:
            return name if name in {"__import__", "globals", "__package__"} else None
        if name in self.globals:
            return self.module.resolve(name)
        return self.parent.resolve(name)


class ImportBindings(ast.NodeVisitor):
    def __init__(self):
        self.scope = ImportScope()
        self.calls = []

    @contextmanager
    def body_scope(self, kind):
        outer = self.scope
        parent = outer.parent if outer.kind == "class" else outer
        self.scope = ImportScope(parent, kind)
        try:
            yield
        finally:
            self.scope = outer

    def visit_Import(self, node):
        for alias in node.names:
            module, _, child = alias.name.partition(".")
            value = module if module in IMPORT_LOADERS else None
            if child and alias.asname:
                value = None
            self.scope.bind(alias.asname or module, value)

    def visit_ImportFrom(self, node):
        loader = IMPORT_LOADERS.get(node.module) if not node.level else None
        for alias in node.names:
            self.scope.bind(
                alias.asname or alias.name, loader if alias.name == loader else None
            )

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.scope.bind(node.id)

    def visit_Global(self, node):
        self.scope.globals.update(node.names)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.scope.bind(node.name)
        self.generic_visit(node)

    visit_MatchAs = visit_ExceptHandler
    visit_MatchStar = visit_ExceptHandler

    def visit_MatchMapping(self, node):
        if node.rest:
            self.scope.bind(node.rest)
        self.generic_visit(node)

    def visit_Call(self, node):
        self.calls.append((node, self.scope))
        self.generic_visit(node)

    def visit_header(self, node):
        for field, value in ast.iter_fields(node):
            if field == "body":
                continue
            if isinstance(value, ast.AST):
                self.visit(value)
            elif isinstance(value, list):
                for child in value:
                    self.visit(child)

    def visit_FunctionDef(self, node):
        self.scope.bind(node.name)
        self.visit_header(node)
        with self.body_scope("function"):
            self.bind_parameters(node.args)
            for child in node.body:
                self.visit(child)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self.visit(node.args)
        with self.body_scope("function"):
            self.bind_parameters(node.args)
            self.visit(node.body)

    def bind_parameters(self, args):
        for param in (
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
            args.vararg,
            args.kwarg,
        ):
            if param is not None:
                self.scope.bind(param.arg)

    def visit_ClassDef(self, node):
        self.scope.bind(node.name)
        self.visit_header(node)
        with self.body_scope("class"):
            for child in node.body:
                self.visit(child)

    def visit_ListComp(self, node):
        first, *rest = node.generators
        self.visit(first.iter)
        with self.body_scope("comprehension"):
            self.visit(first.target)
            for condition in first.ifs:
                self.visit(condition)
            for generator in rest:
                self.visit(generator)
            if isinstance(node, ast.DictComp):
                self.visit(node.key)
                self.visit(node.value)
            else:
                self.visit(node.elt)

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_NamedExpr(self, node):
        self.visit(node.value)
        scope = self.scope
        while scope.kind == "comprehension":
            scope = scope.parent
        scope.bind(node.target.id)


def call_argument(call, position, keyword):
    if position < len(call.args):
        return call.args[position]
    return next((arg.value for arg in call.keywords if arg.arg == keyword), None)


def builtin_request(call, requested, package, scope):
    if requested.startswith("."):
        return None
    level = call_argument(call, 4, "level")
    if level is None:
        return requested
    if not isinstance(level, ast.Constant) or not isinstance(level.value, int):
        return None
    if not 0 <= level.value <= package.count(".") + 1:
        return None
    if not level.value:
        return requested
    context = call_argument(call, 1, "globals")
    if (
        isinstance(context, ast.Call)
        and isinstance(context.func, ast.Name)
        and scope.resolve(context.func.id) == "globals"
        and not (context.args or context.keywords)
    ):
        return "." * level.value + requested
    return None


def literal_import_targets(call, loader, package, scope):
    name = call_argument(call, 0, "name")
    if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
        return []
    requested = name.value
    anchor = package
    if loader == "__import__":
        requested = builtin_request(call, requested, package, scope)
        if requested is None:
            return []
    elif requested.startswith("."):
        context = call_argument(call, 1, "package")
        if isinstance(context, ast.Constant) and isinstance(context.value, str):
            anchor = context.value
        elif (
            not isinstance(context, ast.Name)
            or scope.resolve(context.id) != "__package__"
        ):
            return []
    try:
        imported = importlib.util.resolve_name(requested, anchor)
    except ImportError:
        return []
    targets = [imported]
    if loader == "__import__":
        fromlist = call_argument(call, 3, "fromlist")
        if isinstance(fromlist, (ast.List, ast.Tuple, ast.Set)):
            targets.extend(
                f"{imported}.{item.value}"
                for item in fromlist.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
    return targets


def literal_imports(tree, package):
    bindings = ImportBindings()
    bindings.visit(tree)
    for node, scope in bindings.calls:
        target = node.func
        if isinstance(target, ast.Name):
            loader = scope.resolve(target.id)
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            module = scope.resolve(target.value.id)
            loader = target.attr if IMPORT_LOADERS.get(module) == target.attr else None
        else:
            loader = None
        if loader in IMPORT_LOADERS.values():
            yield node, literal_import_targets(node, loader, package, scope)
