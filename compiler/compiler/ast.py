import ast
import contextlib

from .immutable import immutable


class Node(immutable):
    __slots__ = ()

    def __hash__(self):
        return hash(
            (type(self),) + tuple(getattr(self, s) for s in self.__slots__)
        )

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.to_dict() == other.to_dict()


class ArrayLiteral(Node):
    __slots__ = 'value',

    type = 'array'


class UIntLiteral(Node):
    __slots__ = 'value',

    type = 'uint'


class For(Node):
    __slots__ = 'target', 'iterator', 'body'


class Assignment(Node):
    __slots__ = 'lhs', 'rhs'


class FunctionDef(Node):
    __slots__ = 'name', 'args', 'locals', 'body', 'return_type'

    def __hash__(self):
        return hash((type(self), self.name))

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.name == other.name


class Return(Node):
    __slots__ = 'value',


class Argument(Node):
    __slots__ = 'name', 'type'

    def __hash__(self):
        return hash((type(self), self.name))

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.name == other.name


class Local(Node):
    __slots__ = 'name', 'type'

    def __hash__(self):
        return hash((type(self), self.name))

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.name == other.name


class Global(Node):
    __slots__ = 'name', 'type', 'value'

    def __hash__(self):
        return hash((type(self), self.name))

    def __eq__(self, other):
        if not isinstance(other, __class__):  # noqa
            return NotImplemented

        return self.name == other.name


class Call(Node):
    __slots__ = 'function', 'args', 'type'


class BuiltinCall(Node):
    __slots__ = 'name', 'args', 'type'

    valid = {
        'len': ((Argument('arr', 'array'),), 'uint'),
        'putchar': ((Argument('c', 'uint'),), 'void'),
        'alloc': ((Argument('size', 'uint'),), 'array'),
        'free': ((Argument('arr', 'array'),), 'void'),
        'exit': ((), 'void'),
    }


class BinOp(Node):
    __slots__ = 'op', 'lhs', 'rhs'

    type = 'uint'


class UnOp(Node):
    __slots__ = 'op', 'operand'

    type = 'uint'


class Subscript(Node):
    __slots__ = 'array', 'index'

    type = 'uint'


class IfBranch(Node):
    __slots__ = 'body',


class If(Node):
    __slots__ = 'test', 'true', 'false'


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

        if node.id not in ('uint', 'array', 'void'):
            self.syntax_error(node, 'type must be uint, array or void')

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
                locals=tuple(
                    v
                    for n, (k, v) in enumerate(t.namespace.items())
                    if k not in argnames
                ),
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

    _binoptable = {
        ast.Add: '+',
        ast.Sub: '-',
        ast.Mult: '*',
        ast.Div: '/',
    }

    def visit_BinOp(self, node):
        try:
            op = self._binoptable[type(node.op)]
        except KeyError:
            self.syntax_error(node, 'unknown operator')

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

    _unoptable = {
        ast.UAdd: '+',
        ast.USub: '-',
        ast.Invert: '~',
        ast.Not: 'not',
    }

    def visit_UnaryOp(self, node):
        try:
            op = self._unoptable[type(node.op)]
        except KeyError:
            self.syntax_error(node, 'unknown operator')

        with self.scoped_body() as operand:
            self.visit(node.operand)

        if len(operand) != 1:
            self.syntax_error(node.operand, 'invalid unary operand')

        self.body.append(UnOp(op, operand[0]))

    def visit_Return(self, node):
        if node.value is None:
            if self.return_type == 'array':
                self.body.append(Return(ArrayLiteral([])))
            elif self.return_type == 'uint':
                self.body.append(Return(UIntLiteral(0)))
            else:
                self.body.Append(Return(None))
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
            qualname = f'um.{name}'
            arg_defs, return_type = BuiltinCall.valid[name]
        elif not isinstance(node.func, ast.Name):
            self.syntax_error(node.func, 'function must be a name')
        elif node.func.id not in self.functions:
            self.syntax_error(node.func, 'unknown function')
        else:
            type_ = Call
            qualname = name = node.func.id
            arg_defs, return_type = self.functions[name]

        with self.scoped_body() as args:
            for arg in node.args:
                self.visit(arg)

        if len(args) != len(arg_defs):
            self.syntax_error(
                node,
                f'function {qualname} expects {len(arg_defs)}'
                f' argument{"s" if len(arg_defs) != 1 else ""} but was'
                f' passed {len(args)}',
            )

        it = enumerate(zip(node.args, args, arg_defs))
        for n, (py_node, arg_node, arg_definition) in it:
            if arg_node.type != arg_definition.type:
                self.syntax_error(
                    py_node,
                    f'argument {n} is expected to be of type'
                    f' {arg_definition.type} but got value of type'
                    f' {arg_node.type}',
                )

        self.body.append(type_(name, tuple(args), return_type))

    def visit_For(self, node):
        if node.orelse:
            self.syntax_error(node, 'UML does not support for-else')

        with self.scoped_body() as target:
            self.visit(node.target)

        if not target:
            if not isinstance(node.target, ast.Name):
                self.syntax_error(node.target, 'invalid loop target')

            name = node.target.id
            self.namespace[name] = target = Local(name, 'uint')
        else:
            assert len(target) == 1, (
                f'incorrect number of target nodes: {target}'
            )
            target, = target

        if not isinstance(target, (Local, Argument)):
            self.syntax_error(node.target, 'invalid loop target')

        with self.scoped_body() as iterator:
            self.visit(node.iter)

        assert len(iterator) == 1, (
            f'incorrect number of iterator nodes: {iterator}'
        )
        iterator, = iterator
        if iterator.type != 'array':
            self.syntax_error(
                node.iter,
                f'cannot iterate over values of type {iterator.type}',
            )

        with self.scoped_body() as body:
            for n in node.body:
                self.visit(n)

        self.body.append(For(
            target,
            iterator,
            body,
        ))

    def visit_If(self, node):
        with self.scoped_body() as test:
            self.visit(node.test)

        if len(test) != 1:
            self.syntax_error(node.test, 'invalid condition')

        test, = test
        if test.type != 'uint':
            self.syntax_error(
                node.test,
                f'condition must be of type uint, got expression of type'
                f' {test.type}',
            )

        with self.scoped_body() as true:
            for n in node.body:
                self.visit(n)

        with self.scoped_body() as false:
            for n in node.orelse:
                self.visit(n)

        self.body.append(If(
            test,
            IfBranch(tuple(true)),
            IfBranch(tuple(false)),
        ))

    def visit_Subscript(self, node):
        with self.scoped_body() as arr:
            self.visit(node.value)

        if len(arr) != 1:
            self.syntax_error(node.value, 'invalid array for subscript')

        arr, = arr
        if arr.type != 'array':
            self.syntax_error(node.value, 'can only index arrays')

        with self.scoped_body() as ix:
            self.visit(node.slice)

        if not len(ix) == 1:
            self.syntax_error(node.slice, 'invalid index')
        ix, = ix

        if ix.type != 'uint':
            self.syntax_error(node.slice, 'index must be a uint')

        self.body.append(Subscript(arr, ix))

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            if node.id not in self.namespace and node.id not in self.globals:
                self.syntax_error(node, f'undefined variable {node.id!r}')

            if node.id in self.namespace:
                self.body.append(self.namespace[node.id])
            else:
                self.body.append(self.globals[node.id])

    def _assign_name_lhs(self, node, target):
        name = target.id
        try:
            return self.namespace[name]
        except KeyError:
            self.syntax_error(target, f'undefined variable {name!r}')

    def _assign_subscript_lhs(self, node, target):
        with self.scoped_body() as lhs:
            self.visit(target)

        if not len(lhs) == 1:
            self.syntax_error(target, 'invalid assignment target')

        return lhs[0]

    def visit_Assign(self, node):
        if len(node.targets) > 1:
            self.syntax_error(node, 'UML does not support multiple assignment')

        target, = node.targets
        if not isinstance(target, (ast.Name, ast.Subscript)):
            self.syntax_error(target, 'invalid lhs')

        with self.scoped_body() as rhs_nodes:
            self.visit(node.value)

        assert len(rhs_nodes) == 1, (
            f'incorrect number of rhs nodes: {rhs_nodes}'
        )
        rhs, = rhs_nodes

        if isinstance(target, ast.Name):
            lhs = self._assign_name_lhs(node, target)
        elif isinstance(target, ast.Subscript):
            lhs = self._assign_subscript_lhs(node, target)
        else:
            self.syntax_error(target, 'invalid assignment target')

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
