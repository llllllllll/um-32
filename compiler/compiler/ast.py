import ast
import contextlib

from .immutable import immutable


class ArrayLiteral(immutable):
    __slots__ = 'value',

    type = 'array'

    def __hash__(self):
        return hash((type(self), self.value))

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.value == other.value


class UIntLiteral(immutable):
    __slots__ = 'value',

    type = 'uint'


class For(immutable):
    __slots__ = 'target', 'iterator', 'body'


class Assignment(immutable):
    __slots__ = 'lhs', 'rhs'


class FunctionDef(immutable):
    __slots__ = 'name', 'args', 'locals', 'body', 'return_type'

    def __hash__(self):
        return hash((type(self), self.name))

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.name == other.name


class Return(immutable):
    __slots__ = 'value',


class Argument(immutable):
    __slots__ = 'name', 'type'

    def __hash__(self):
        return hash((type(self), self.name))

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.name == other.name


class Local(immutable):
    __slots__ = 'name', 'type'

    def __hash__(self):
        return hash((type(self), self.name))

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.name == other.name


class Global(immutable):
    __slots__ = 'name', 'type', 'value'

    def __hash__(self):
        return hash((type(self), self.name))

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.name == other.name


class Call(immutable):
    __slots__ = 'function', 'args', 'type'


class BuiltinCall(immutable):
    __slots__ = 'name', 'args', 'type'

    valid = {
        'putchar': ((Argument('c', 'uint'),), 'void'),
    }


class BinOp(immutable):
    __slots__ = 'op', 'lhs', 'rhs'

    type = 'uint'


class _AstTranslator(ast.NodeVisitor):
    def __init__(self, globals, functions, body, filename, lines):
        self.globals = globals
        self.functions = functions
        self.body = body
        self.filename = filename
        self.lines = lines

    @contextlib.contextmanager
    def scoped_body(self):
        old_body = self.body
        self.body = body = []
        try:
            yield body
        finally:
            self.body = old_body

    def syntax_error(self, node, msg='invalid syntax'):
        raise SyntaxError(
            msg, (
                self.filename,
                node.lineno,
                node.col_offset + 1,
                self.lines[node.lineno - 1],
            ),
        )

    def process_annotation(self, node, context):
        if node is None:
            self.syntax_error(context, 'missing type information')

        if not isinstance(node, ast.Name):
            self.syntax_error(node, 'type must be a name')

        if node.id not in ('uint', 'array'):
            self.syntax_error(node, 'type must be uint or array')

        return node.id

    def visit_Num(self, node):
        n = node.n
        if n < 0 or n > 2 ** 32 - 1:
            self.syntax_error(node, 'literal does not fit in a uint')

        self.body.append(UIntLiteral(n))

    def visit_Str(self, node):
        s = node.s

        try:
            s = s.encode('ascii')
        except ValueError:
            self.syntax_error(node, 'string literal must be ascii')

        self.body.append(ArrayLiteral(tuple(s)))

    def visit_List(self, node):
        es = []
        for e in node.elts:
            if not isinstance(e, ast.Num):
                self.syntax_error(e, 'array literal may only contain uints')

            n = e.n
            if n < 0 or n > 2 ** 32 - 1:
                self.syntax_error(e, 'literal does not fit in a uint')

            es.append(n)

        self.body.append(ArrayLiteral(tuple(es)))

    def visit_NameConstant(self, node):
        value = node.value
        if value is None:
            self.body.append(UIntLiteral(0))
        elif value is True:
            self.body.append(UIntLiteral(1))
        elif value is False:
            self.body.append(UIntLiteral(0))

    def _outside_body(self, node):
        self.syntax_error(
            node,
            'cannot execute code outside of a function body',
        )

    visit_Call = _outside_body
    visit_For = _outside_body

    def _undefined(self, node):
        self.syntax_error(
            node,
            f'UML does not support {type(node).__name__.lower()} statements'
        )

    visit_With = _undefined
    visit_Import = _undefined
    visit_ImportWith = _undefined

    def visit_Assign(self, node):
        self.syntax_error(node, 'global assignment requires a type')

    def process_function_args(self, node):
        if node.vararg:
            self.syntax_error(node, 'variadic functions are not yet supported')

        if node.kwonlyargs or node.kw_defaults or node.kwarg:
            self.syntax_error(node, 'UML does not support keyword arguments')

        if node.defaults:
            self.syntax_error(node, 'UML does not support argument defaults')

        return [
            Argument(arg.arg, self.process_annotation(arg.annotation, arg))
            for arg in node.args
        ]


class _GlobalFinder(_AstTranslator):
    def visit_AnnAssign(self, node):
        target = node.target
        if not isinstance(target, ast.Name):
            self.syntax_error(target, 'invalid lhs')

        name = target.id
        if name in self.globals:
            self.syntax_error(f'redefinition of global variable {name!r}')

        type_ = self.process_annotation(node.annotation, node)
        with self.scoped_body() as rhs_nodes:
            self.visit(node.value)

        assert len(rhs_nodes) == 1, (
            f'incorrect number of  rhs nodes: {rhs_nodes}'
        )
        rhs, = rhs_nodes

        if rhs.type != type_:
            self.syntax_error(
                node,
                f'invalid assignment lhs :: {type_}, rhs :: {rhs.type}',
            )

        self.globals[name] = Global(name, type_, rhs)

    def visit_FunctionDef(self, node):
        if node.name in self.functions:
            self.syntax_error(node, 'redefinition of function {node.name!r}')

        args = self.process_function_args(node.args)
        return_type = self.process_annotation(node.returns, node)

        self.functions[node.name] = args, return_type


class _TopLevelTranslator(_AstTranslator):
    def visit_FunctionDef(self, node):
        if node.decorator_list:
            self.syntax_error(node, 'UML does not support decorators')

        args, return_type = self.functions[node.name]
        body = []
        t = _FunctionTranslator(
            args,
            return_type,
            self.globals,
            self.functions,
            body,
            self.filename,
            self.lines,
        )
        for n in node.body:
            t.visit(n)

        argnames = {arg.name for arg in args}
        self.body.append(
            FunctionDef(
                name=node.name,
                args=args,
                locals=[
                    v
                    for n, (k, v) in enumerate(t.namespace.items())
                    if k not in argnames
                ],
                body=body,
                return_type=return_type,
            ),
        )


class _FunctionTranslator(_AstTranslator):
    def __init__(self, arguments, return_type, *args, **kwarg):
        super().__init__(*args, **kwarg)
        self.namespace = {arg.name: arg for arg in arguments}
        self._return_type = return_type

    def visit_FunctionDef(self, node):
        self.syntax_error(node, 'UML does not support closures')

    _optable = {
        ast.Add: '+',
        ast.Sub: '-',
        ast.Mult: '*',
        ast.Div: '/',
    }

    def visit_BinOp(self, node):
        try:
            op = self._optable[type(node.op)]
        except KeyError:
            self.syntax_error(node.op, 'unknown operator')

        with self.scoped_body() as operands:
            self.visit(node.left)
            self.visit(node.right)

        assert len(operands) == 2, f'incorrect number of operands: {operands}'
        lhs, rhs = operands

        if lhs.type != 'uint':
            self.syntax_error(
                node.left,
                f'cannot add operand of type {lhs.type}',
            )
        if rhs.type != 'uint':
            self.syntax_error(
                node.right,
                f'cannot add operand of type {rhs.type}',
            )
        self.body.append(BinOp(op, lhs, rhs))

    def visit_Return(self, node):
        if node.value is None:
            if self.return_type == 'array':
                self.body.append(Return(ArrayLiteral([])))
            else:
                self.body.append(Return(UIntLiteral(0)))
            return

        with self.scoped_body() as return_value:
            self.visit(node.value)

        assert len(return_value) == 1, (
            f'incorrect number of return value nodes: {return_value}'
        )

        return_node, = return_value
        if return_node.type != self._return_type:
            self.syntax_error(
                node.value,
                f'cannot return value of type {return_node.type} in a'
                f' function with return type {self._return_type}',
            )

        self.body.append(Return(return_node))

    def visit_Call(self, node):
        if (isinstance(node.func, ast.Attribute) and
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == 'um'):
            if node.func.attr not in BuiltinCall.valid:
                self.syntax_error(node.func.value, 'unknown builtin function')
            type_ = BuiltinCall
            name = node.func.attr
            arg_defs, return_type = BuiltinCall.valid[name]
        elif not isinstance(node.func, ast.Name):
            self.syntax_error(node.func, 'function must be a name')
        elif node.func.id not in self.functions:
            self.syntax_error(node.func, 'unknown function')
        else:
            type_ = Call
            name = node.func.id
            arg_defs, return_type = self.functions[name]

        with self.scoped_body() as args:
            for arg in node.args:
                self.visit(arg)

        it = enumerate(zip(node.args, args, arg_defs))
        for n, (py_node, arg_node, arg_definition) in it:
            if arg_node.type != arg_definition.type:
                self.syntax_error(
                    py_node,
                    f'argument {n} is expected to be of type'
                    f' {arg_definition.type} but got value of type'
                    f' {arg_node.type}',
                )

        self.body.append(type_(name, args, return_type))

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            if node.id not in self.namespace and node.id not in self.globals:
                self.syntax_error(node, f'undefined variable {node.id!r}')

            if node.id in self.namespace:
                self.body.append(self.namespace[node.id])
            else:
                self.body.append(self.globals[node.id])

    def visit_Assign(self, node):
        if len(node.targets) > 1:
            self.syntax_error(node, 'UML does not support multiple assignment')

        target, = node.targets
        if not isinstance(target, ast.Name):
            self.syntax_error(target, 'invalid lhs')

        name = target.id
        if name not in self.namespace:
            self.process_annotation(None, target)

        with self.scoped_body() as rhs_nodes:
            self.visit(node.value)

        assert len(rhs_nodes) == 1, (
            f'incorrect number of rhs nodes: {rhs_nodes}'
        )
        rhs, = rhs_nodes

        lhs = self.namespace[name]

        if rhs.type != lhs.type:
            self.syntax_error(
                node,
                f'invalid assignment lhs :: {lhs.type}, rhs :: {rhs.type}',
            )

        self.body.append(Assignment(lhs, rhs))

    def visit_AnnAssign(self, node):
        target = node.target
        if not isinstance(target, ast.Name):
            self.syntax_error(target, 'invalid lhs')

        name = target.id
        if name in self.namespace:
            self.syntax_error(node, f'redefinition of local variable {name!r}')

        type_ = self.process_annotation(node.annotation, node)
        with self.scoped_body() as rhs_nodes:
            self.visit(node.value)

        assert len(rhs_nodes) == 1, (
            f'incorrect number of  rhs nodes: {rhs_nodes}'
        )
        rhs, = rhs_nodes

        if rhs.type != type_:
            self.syntax_error(
                node,
                f'invalid assignment lhs :: {type_}, rhs :: {rhs.type}',
            )

        lhs = Local(name, type_)
        self.namespace[name] = lhs
        self.body.append(Assignment(lhs, rhs))


def parse(source, filename='<unknown>'):
    tree = ast.parse(source, filename=filename)
    lines = source.splitlines()

    globals_ = {}
    functions = {}

    _GlobalFinder(globals_, functions, [], lines, filename).visit(tree)

    body = []
    _TopLevelTranslator(
        globals_,
        functions,
        body,
        filename,
        source.splitlines(),
    ).visit(tree)
    return body
