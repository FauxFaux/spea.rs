import ast
import inspect
import sys
from typing import List


class Visit(ast.NodeVisitor):
    def __init__(self):
        self.scope = []  # type: List[str]

    def at_global_scope(self):
        return not self.scope

    def whitespace(self):
        return '\n' + ('   ' * len(self.scope))

    def safe_let(self, thing):
        if isinstance(thing, ast.Name) and not self.at_global_scope()\
                and ['class'] != self.scope\
                and 'for' not in self.scope and 'while' not in self.scope:
            yield 'let '

        if thing:
            yield from self.visit(thing)

    def generic_visit(self, node: ast.AST):
        raise Exception(node)

    def recurse(self, node: ast.AST):
        for child in ast.iter_child_nodes(node):
            yield from self.visit(child)

    def visit_Module(self, node: ast.Module):
        yield '/* module */'
        yield from self.doc_body(node)

    def doc_body(self, node):
        fiddled = list(node.body)
        possible_docstring = fiddled[0]
        if isinstance(possible_docstring, ast.Expr) and \
                isinstance(possible_docstring.value, ast.Str):
            fiddled.pop(0)
            docstring = inspect.cleandoc(possible_docstring.value.s)
            yield self.whitespace().join('// {}'.format(x) for x in docstring.split('\n')) + self.whitespace()

        for item in fiddled:
            yield from self.visit(item)

    def visit_Expr(self, node: ast.Expr):
        # yield '/* expr */'
        yield from self.recurse(node)
        yield ';' + self.whitespace()

    def visit_Str(self, node: ast.Str):
        yield rust_str(node.s)

    def visit_Import(self, node: ast.Import):
        for name in node.names:
            yield 'use {};{}'.format(strip_alias(name), self.whitespace())

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for mod in node.names:
            yield 'use {}::{};{}'.format(node.module.replace('.', '::'), strip_alias(mod.name), self.whitespace())

    def visit_Assign(self, node: ast.Assign):
        gen_const = self.at_global_scope() or self.scope == ['class']
        if gen_const:
            yield 'const '
        if len(node.targets) == 1:
            thing = node.targets[0]
            if isinstance(thing, ast.Tuple):
                yield 'let '
                yield from self.call_list(thing.elts)
            else:
                yield from self.safe_let(thing)
        else:
            yield from self.safe_let(None)
            yield from self.call_list(node.targets)

        if gen_const:
            yield ': Unknown'
        yield ' = '
        yield from self.visit(node.value)
        yield ';' + self.whitespace()

    def call_list(self, some):
        yield '('
        for (i, item) in enumerate(some):
            yield from self.visit(item)
            if i != len(some) - 1:
                yield ', '
        yield ')'

    def visit_Store(self, node: ast.Store):
        yield '/* store */'

    def visit_Name(self, node: ast.Name):
        # yield '/* name */'
        yield node.id

    def visit_Call(self, node: ast.Call):
        # yield '/* call */'
        yield from self.visit(node.func)
        yield '('
        for (i, arg) in enumerate(node.args):
            yield from self.visit(arg)
            if len(node.args) - 1 != i:
                yield ','
        yield ')'

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        yield 'panic!(' + rust_str(ast.dump(node)) + ')'

    def visit_ListComp(self, node: ast.GeneratorExp):
        yield 'panic!(' + rust_str(ast.dump(node)) + ')'

    def visit_SetComp(self, node: ast.GeneratorExp):
        yield 'panic!(' + rust_str(ast.dump(node)) + ')'

    def visit_DictComp(self, node: ast.GeneratorExp):
        yield 'panic!(' + rust_str(ast.dump(node)) + ')'

    def visit_ClassDef(self, node: ast.ClassDef):
        self.scope.append('class')
        yield 'impl ' + node.name + '{' + self.whitespace()
        yield from self.doc_body(node)
        self.scope.pop()
        yield '}' + self.whitespace()

    def visit_Tuple(self, node: ast.Tuple):
        yield '('
        for (i, element) in enumerate(node.elts):
            yield from self.visit(element)
            if i != len(node.elts) - 1:
                yield ', '
        yield ')'

    def visit_BinOp(self, node: ast.BinOp):
        if isinstance(node.op, ast.Mod):
            yield 'format!('
            assert isinstance(node.left, ast.Str)
            yield rust_str(node.left.s.replace('%s', '{}').replace('%d', '{}'))
            if isinstance(node.right, ast.Tuple):
                for item in node.right.elts:
                    yield ', '
                    yield from self.visit(item)
            else:
                yield ', '
                yield from self.visit(node.right)

            yield ')'
            return

        yield from self.visit(node.left)
        yield from self.visit(node.op)
        yield from self.visit(node.right)

    def visit_Add(self, node: ast.Add):
        yield '+'

    def visit_Sub(self, node: ast.Add):
        yield '-'

    def visit_Not(self, node: ast.Not):
        yield '!'

    def visit_BitOr(self, node: ast.Not):
        yield '|'

    def visit_BitAnd(self, node: ast.Not):
        yield '&'

    def visit_IsNot(self, node: ast.IsNot):
        yield '/* is not */ !='

    def visit_And(self, node: ast.And):
        yield ' && '

    def visit_Or(self, node: ast.Or):
        yield ' || '

    def visit_Eq(self, node: ast.NotEq):
        yield ' == '

    def visit_Is(self, node: ast.NotEq):
        yield ' /* is */ == '

    def visit_NotEq(self, node: ast.NotEq):
        yield ' != '

    def visit_USub(self, node: ast.USub):
        yield '-'

    def visit_Gt(self, node):
        yield '>'

    def visit_Lt(self, node):
        yield '<'

    def visit_LtE(self, node):
        yield '<='

    def visit_GtE(self, node):
        yield '>='

    def visit_FunctionDef(self, node: ast.FunctionDef):
        assert isinstance(node.args, ast.arguments)
        args = node.args

        yield 'fn {}<{}> ('.format(
            node.name,
            ', '.join(['T{}'.format(i) for i in range(len(node.args.args))])
        )

        yield from self.render_arguments(node.args, True)
        yield ')'

        if node.returns:
            yield ' -> '
            yield from self.visit(node.returns)
        self.scope.append('method')
        yield '{' + self.whitespace()
        yield from self.doc_body(node)
        self.scope.pop()
        yield '}\n' + self.whitespace()

    def render_arguments(self, node: ast.arguments, types: bool):
        assert not node.vararg
        assert not node.kwonlyargs
        # assert not node.defaults
        yield '/* TODO: unimplemented: defaults */'
        assert not node.kwarg
        assert not node.kw_defaults

        for (i, arg) in enumerate(node.args):
            assert isinstance(arg, ast.arg)
            if 0 == i and 'self' == arg.arg:
                yield '&self'
            else:
                yield arg.arg
                if types:
                    yield ': T{}'.format(i)

            if i != len(node.args) - 1:
                yield ', '

    def visit_Attribute(self, node: ast.Attribute):
        yield from self.visit(node.value)
        yield '.'
        yield node.attr

    def visit_List(self, node: ast.List):
        if 0 == len(node.elts):
            yield 'Vec::new()'
            return
        yield 'vec!('
        for item in node.elts:
            yield from self.visit(item)
            yield ', '
        yield ')'

    def visit_Dict(self, node: ast.Dict):
        if 0 == len(node.keys):
            yield 'HashMap::new()'
            return

        yield 'hashmap!(' + self.whitespace()
        for i in range(len(node.keys)):
            yield from self.visit(node.keys[i])
            yield ' => '
            yield from self.visit(node.values[i])
            yield ',' + self.whitespace()
        yield ')'

    def visit_Try(self, node: ast.Try):
        self.scope.append('try')
        yield 'if /* try */ !{' + self.whitespace()
        for item in node.body:
            yield from self.visit(item)
        yield '} {' + self.whitespace()
        if len(node.handlers) > 1:
            yield 'panic!("multilple handlers:");' + self.whitespace()
        for handler in node.handlers:
            yield from self.visit(handler)
        self.scope.pop()
        yield '}\n' + self.whitespace()

        assert not node.orelse

        for item in node.finalbody:
            yield from self.visit(item)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        yield '/* '
        yield from self.visit(node.type)
        yield ' */'
        for item in node.body:
            yield from self.visit(item)

    def visit_Subscript(self, node: ast.Subscript):
        yield from self.visit(node.value)
        yield '['
        yield from self.visit(node.slice)
        yield ']'

    def visit_Index(self, node: ast.Index):
        yield from self.recurse(node)

    def visit_If(self, node: ast.If):
        if self.at_global_scope()\
                and isinstance(node.test, ast.Compare)\
                and isinstance(node.test.left, ast.Name)\
                and node.test.left.id == '__name__':
            yield '/* TODO: skipped if __name__ hack */'
            return
        yield 'if '
        yield from self.visit(node.test)
        self.scope.append('if')
        yield ' {' + self.whitespace()
        for item in node.body:
            yield from self.visit(item)
        if node.orelse:
            yield '} else {'
            for item in node.orelse:
                yield from self.visit(item)

        self.scope.pop()
        yield '}\n' + self.whitespace()

    def visit_IfExp(self, node: ast.IfExp):
        yield 'if '
        yield from self.visit(node.test)
        yield ' {' + self.whitespace()
        yield from self.visit(node.body)
        yield '} else {'
        yield from self.visit(node.orelse)
        yield '}'

    def visit_Return(self, node: ast.Return):
        yield 'return '
        if node.value:
            yield from self.visit(node.value)
        yield ';' + self.whitespace()

    def visit_Continue(self, node: ast.Continue):
        yield 'continue;' + self.whitespace()

    def visit_Break(self, node: ast.Break):
        yield 'break;' + self.whitespace()

    def visit_For(self, node: ast.For):
        yield 'for '
        yield from self.visit(node.target)
        yield ' in '
        yield from self.visit(node.iter)
        self.scope.append('for')
        yield ' {' + self.whitespace()
        for item in node.body:
            yield from self.visit(item)
        self.scope.pop()
        yield '}' + self.whitespace()

    def visit_Compare(self, node: ast.Compare):
        assert 1 == len(node.ops)

        if isinstance(node.ops[0], ast.In) or isinstance(node.ops[0], ast.NotIn):
            assert 1 == len(node.comparators)
            if isinstance(node.ops[0], ast.NotIn):
                yield '!'
            yield from self.visit(node.comparators[0])
            yield '.contains_key('
            yield from self.visit(node.left)
            yield ')'
            return

        assert 1 == len(node.comparators)
        yield from self.visit(node.left)
        yield from self.visit(node.ops[0])
        yield from self.visit(node.comparators[0])

    def visit_NameConstant(self, node: ast.NameConstant):
        yield repr(node.value)

    def visit_BoolOp(self, node: ast.BoolOp):
        it = iter(node.values)
        yield from self.visit(next(it))
        for item in it:
            yield from self.visit(node.op)
            yield from self.visit(item)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        yield from self.visit(node.op)
        yield from self.visit(node.operand)

    def visit_Lambda(self, node: ast.Lambda):
        yield '|'
        self.render_arguments(node.args, False)
        yield '| '
        yield from self.visit(node.body)

    def visit_Raise(self, node: ast.Raise):
        yield '/* raise */ return Err('
        yield from self.visit(node.exc)
        yield ');' + self.whitespace()

    def visit_Assert(self, node: ast.Assert):
        yield 'assert!('
        yield from self.visit(node.test)
        yield ');' + self.whitespace()

    def visit_Num(self, node: ast.Num):
        yield repr(node.n)

    def visit_With(self, node: ast.With):
        self.scope.append('with')
        yield '{/* <with block> */' + self.whitespace()
        for item in node.items:
            yield from self.safe_let(item)
            yield ';' + self.whitespace()
        yield self.whitespace() + '/* <-> */' + self.whitespace()

        for item in node.body:
            yield from self.visit(item)

        self.scope.pop()
        yield '}/* </with block> */\n' + self.whitespace()

    def visit_withitem(self, node: ast.withitem):
        yield from self.visit(node.optional_vars)
        yield ' = '
        yield from self.visit(node.context_expr)

    def visit_Set(self, node: ast.Set):
        yield 'hashset!('
        for (i, val) in enumerate(node.elts):
            yield from self.visit(val)
            if i != len(node.elts) - 1:
                yield ', '
        yield ')'

    def visit_AugAssign(self, node: ast.AugAssign):
        yield from self.visit(node.target)
        yield ' '
        yield from self.visit(node.op)
        yield '= '
        yield from self.visit(node.value)
        yield ';' + self.whitespace()

    def visit_While(self, node: ast.While):
        yield 'while '
        yield from self.visit(node.test)
        self.scope.append('while')
        yield '{' + self.whitespace()
        for item in node.body:
            yield from self.visit(item)
        self.scope.pop()
        yield '}' + self.whitespace()

        assert not node.orelse

    def visit_Slice(self, node: ast.Slice):
        assert not node.step
        if node.lower:
            yield from self.visit(node.lower)
        yield '..'
        if node.upper:
            yield from self.visit(node.upper)

    def visit_Delete(self, node: ast.Delete):
        yield 'panic!(' + rust_str(ast.dump(node)) + ');' + self.whitespace()


def strip_alias(thing) -> str:
    if hasattr(thing, 'name'):
        return thing.name
    return thing


def rust_str(some_str):
    return '"{}"'.format(some_str.encode('unicode_escape').replace(b'"', b'\\"').decode('utf-8'))


def main():
    source = sys.argv[1]
    with open(source) as f:
        a = ast.parse(f.read(), source)

    for item in Visit().visit(a):
        print(item, end='')


if __name__ == '__main__':
    main()
