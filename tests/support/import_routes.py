"""Resolve literal dynamic import targets using statically known loader bindings."""

import ast
import importlib.util
from contextlib import contextmanager
from functools import partial
from itertools import count

IMPORT_LOADERS = {"importlib": "import_module", "builtins": "__import__"}


class ImportScope:
    def __init__(
        self, parent=None, kind="module", parent_order=None, parent_branches=()
    ):
        self.parent = parent
        self.kind = kind
        self.module = parent.module if parent else self
        self.parent_order = parent_order
        self.parent_branches = parent_branches
        self.bindings = {}
        self.globals = set()
        self.nonlocals = set()

    def values_at(self, name, order, branches):
        events = self.bindings.get(name, ())
        if order is None:
            return {value for _, _, value in events}
        current = dict(branches)
        values = set()
        for when, conditions, value in events:
            if when >= order:
                break
            if any(key in current and current[key] != arm for key, arm in conditions):
                continue
            if all(current.get(key) == arm for key, arm in conditions):
                values.clear()
            values.add(value)
        return values

    def resolve(self, name, order, branches):
        values = self.values_at(name, order, branches)
        if values:
            return next(iter(values)) if len(values) == 1 else None
        if self.parent is None:
            return name if name in {"__import__", "globals", "__package__"} else None
        if name in self.globals:
            return self.module.resolve(name, self.parent_order, self.parent_branches)
        if (
            self.kind in {"function", "comprehension"}
            and name in self.bindings
            and name not in self.nonlocals
        ):
            return None
        return self.parent.resolve(name, self.parent_order, self.parent_branches)


class ImportBindings(ast.NodeVisitor):
    def __init__(self):
        self.scope = ImportScope()
        self.timeline = count()
        self.branches = ()
        self.calls = []

    @contextmanager
    def body_scope(self, kind, *, deferred=False):
        outer = self.scope
        outer_branches = self.branches
        parent = outer.parent if outer.kind == "class" else outer
        parent_order = None if deferred else next(self.timeline)
        self.scope = ImportScope(parent, kind, parent_order, outer_branches)
        self.branches = ()
        try:
            yield
        finally:
            self.scope = outer
            self.branches = outer_branches

    @contextmanager
    def conditional(self, region, arm=True):
        outer = self.branches
        self.branches = (*outer, (region, arm))
        try:
            yield
        finally:
            self.branches = outer

    def bind(self, name, value=None, *, scope=None):
        scope = scope or self.scope
        events = scope.bindings.setdefault(name, [])
        events.append((next(self.timeline), self.branches, value))

    def visit_Import(self, node):
        for alias in node.names:
            module, _, child = alias.name.partition(".")
            value = module if module in IMPORT_LOADERS else None
            if child and alias.asname:
                value = None
            self.bind(alias.asname or module, value)

    def visit_ImportFrom(self, node):
        loader = IMPORT_LOADERS.get(node.module) if not node.level else None
        for alias in node.names:
            self.bind(
                alias.asname or alias.name, loader if alias.name == loader else None
            )

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bind(node.id)

    def visit_Global(self, node):
        self.scope.globals.update(node.names)

    def visit_Nonlocal(self, node):
        self.scope.nonlocals.update(node.names)

    def visit_Assign(self, node):
        self.visit(node.value)
        for target in node.targets:
            self.visit(target)

    def visit_AnnAssign(self, node):
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
            self.visit(node.target)
        elif self.scope.kind == "function":
            self.visit(node.target)

    def visit_If(self, node):
        self.visit(node.test)
        with self.conditional(node):
            for child in node.body:
                self.visit(child)
        with self.conditional(node, False):
            for child in node.orelse:
                self.visit(child)

    def visit_For(self, node):
        self.visit(node.iter)
        with self.conditional(node):
            self.visit(node.target)
            for child in node.body:
                self.visit(child)
        with self.conditional(object()):
            for child in node.orelse:
                self.visit(child)

    visit_AsyncFor = visit_For

    def visit_While(self, node):
        self.visit(node.test)
        with self.conditional(node):
            for child in node.body:
                self.visit(child)
        with self.conditional(object()):
            for child in node.orelse:
                self.visit(child)

    def visit_Try(self, node):
        for part in (node.body, node.handlers, node.orelse):
            with self.conditional(object()):
                for child in part:
                    self.visit(child)
        for child in node.finalbody:
            self.visit(child)

    visit_TryStar = visit_Try

    def visit_Match(self, node):
        self.visit(node.subject)
        for arm, case in enumerate(node.cases):
            with self.conditional(node, arm):
                self.visit(case)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.bind(node.name)
        self.generic_visit(node)

    visit_MatchAs = visit_ExceptHandler
    visit_MatchStar = visit_ExceptHandler

    def visit_MatchMapping(self, node):
        if node.rest:
            self.bind(node.rest)
        self.generic_visit(node)

    def visit_Call(self, node):
        self.calls.append((node, self.scope, next(self.timeline), self.branches))
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
        self.visit_header(node)
        self.bind(node.name)
        with self.body_scope("function", deferred=True):
            self.bind_parameters(node.args)
            for child in node.body:
                self.visit(child)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self.visit(node.args)
        with self.body_scope("function", deferred=True):
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
                self.bind(param.arg)

    def visit_ClassDef(self, node):
        self.visit_header(node)
        with self.body_scope("class"):
            for child in node.body:
                self.visit(child)
        self.bind(node.name)

    def visit_ListComp(self, node):
        first, *rest = node.generators
        self.visit(first.iter)
        with self.body_scope(
            "comprehension", deferred=isinstance(node, ast.GeneratorExp)
        ):
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
        self.bind(node.target.id, scope=scope)


def call_argument(call, position, keyword):
    if position < len(call.args):
        return call.args[position]
    return next((arg.value for arg in call.keywords if arg.arg == keyword), None)


def builtin_request(call, requested, package, resolve):
    if requested.startswith("."):
        return None
    level = call_argument(call, 4, "level")
    if level is None:
        return requested, package
    if not isinstance(level, ast.Constant) or not isinstance(level.value, int):
        return None
    if level.value < 0:
        return None
    if not level.value:
        return requested, package
    context = call_argument(call, 1, "globals")
    if (
        isinstance(context, ast.Call)
        and isinstance(context.func, ast.Name)
        and resolve(context.func.id) == "globals"
        and not (context.args or context.keywords)
    ):
        anchor = package
    elif isinstance(context, ast.Dict):
        try:
            anchor = ast.literal_eval(context).get("__package__")
        except TypeError, ValueError:
            return None
    else:
        return None
    if not isinstance(anchor, str) or not anchor or level.value > anchor.count(".") + 1:
        return None
    return "." * level.value + requested, anchor


def literal_import_targets(call, loader, package, resolve):
    name = call_argument(call, 0, "name")
    if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
        return []
    requested = name.value
    anchor = package
    if loader == "__import__":
        builtin = builtin_request(call, requested, package, resolve)
        if builtin is None:
            return []
        requested, anchor = builtin
    elif requested.startswith("."):
        context = call_argument(call, 1, "package")
        if isinstance(context, ast.Constant) and isinstance(context.value, str):
            anchor = context.value
        elif not isinstance(context, ast.Name) or resolve(context.id) != "__package__":
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
    for node, scope, order, branches in bindings.calls:
        resolve = partial(scope.resolve, order=order, branches=branches)
        target = node.func
        if isinstance(target, ast.Name):
            loader = resolve(target.id)
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            module = resolve(target.value.id)
            loader = target.attr if IMPORT_LOADERS.get(module) == target.attr else None
        else:
            loader = None
        if loader in IMPORT_LOADERS.values():
            yield node, literal_import_targets(node, loader, package, resolve)
