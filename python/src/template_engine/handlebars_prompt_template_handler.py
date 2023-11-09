import asyncio
import json
import threading
from typing import Any

import pybars
from pybars import Compiler
from pydantic import PrivateAttr
from semantic_kernel.sk_pydantic import SKBaseModel


def _message(this, options, **kwargs):
    # single message call, scope is messages object as context
    # in messages loop, scope is ChatMessage object as context
    if "role" in kwargs or "Role" in kwargs:
        role = kwargs.get("role" or "Role")
        if role:
            return f'<message role="{kwargs.get("role") or kwargs.get("Role")}">{options["fn"](this)}</message>'


def _set(this, *args, **kwargs):
    if "name" in kwargs and "value" in kwargs:
        this.context[kwargs["name"]] = kwargs["value"]
    if len(args) == 2 and isinstance(args[0], str):
        this.context[args[0]] = args[1]
    return ""


def _get(this, *args, **kwargs):
    if len(args) == 0:
        return ""
    return this.context.get(args[0], "")


def _array(this, *args, **kwargs):
    return list(args)


def _range(this, *args, **kwargs):
    args = list(args)
    for idx in range(len(args)):
        if not isinstance(args[idx], int):
            try:
                args[idx] = int(args[idx])
            except ValueError:
                args.pop(idx)
    if len(args) == 1:
        return list(range(args[0]))
    return list(range(args[0], args[1]))


def _concat(this, *args, **kwargs):
    return "".join([str(value) for value in kwargs.values()])


def _equal(this, *args, **kwargs):
    return args[0] == args[1]


def _less_than(this, *args, **kwargs):
    return float(args[0]) < float(args[1])


def _greater_than(this, *args, **kwargs):
    return float(args[0]) > float(args[1])


def _less_than_or_equal(this, *args, **kwargs):
    return float(args[0]) <= float(args[1])


def _greater_than_or_equal(this, *args, **kwargs):
    return float(args[0]) >= float(args[1])


def _json(this, *args, **kwargs):
    if not args:
        return ""
    return json.dumps(args[0])


def _double_open(this, *args, **kwargs):
    return "{{"


def _double_close(this, *args, **kwargs):
    return "}}"


def _camel_case(this, *args, **kwargs):
    return "".join([word.capitalize() for word in args[0].split("_")])


# TODO: render functions are helpers


class RunThread(threading.Thread):
    # TODO: replace with better solution and/or figure out why asyncio.run will not work, or move to handlebars implementation that van handle async
    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.result = None
        super().__init__()

    def run(self):
        self.result = asyncio.run(self.func(*self.args, **self.kwargs))


def create_func(function, fixed_kwargs):
    def func(context, *args, **kwargs):
        fixed_kwargs["variables"] = kwargs
        thread = RunThread(func=function.run_async, args=args, kwargs=fixed_kwargs)
        thread.start()
        thread.join()
        return thread.result

    return func


class HandleBarsPromptTemplateHandler(SKBaseModel):
    template: str
    _template_compiler: Any = PrivateAttr()

    def __init__(self, template: str):
        super().__init__(template=template)
        compiler = Compiler()
        pybars.debug = True
        self._template_compiler = compiler.compile(self.template)

    async def render(self, variables: dict, **kwargs) -> str:
        helpers = {
            "message": _message,
            "set": _set,
            "get": _get,
            "array": _array,
            "range": _range,
            "concat": _concat,
            "equal": _equal,
            "lessThan": _less_than,
            "greaterThan": _greater_than,
            "lessThanOrEqual": _less_than_or_equal,
            "greaterThanOrEqual": _greater_than_or_equal,
            "json": _json,
            "doubleOpen": _double_open,
            "doubleClose": _double_close,
            "camelCase": _camel_case,
        }
        kwargs["called_by_template"] = True
        if "plugin_functions" in kwargs:
            plugin_functions = kwargs.get("plugin_functions")
            if plugin_functions:
                helpers.update(
                    {
                        name: create_func(function, kwargs)
                        for name, function in plugin_functions.items()
                    }
                )
        return self._template_compiler(variables, helpers=helpers)
