"""Agent specs: a serializable, hashable description of an agent, and the way back from a spec to an agent.

Every component (memory, critic and its features and prior, actor and its choice rule, percept) derives from `Component`, which
records the arguments it was built with. `component.spec()` is a plain dict: `{"type": <class name>, <parameter>: <value>, ...}`,
with every constructor default resolved and nested components as nested specs. `ComposedAgent.spec()` (agents.py) joins the four
into one agent spec, `build_agent(spec)` rebuilds the agent, and `spec_hash(spec)` is its identity: the first 12 hex characters
of the SHA-256 of the canonical JSON (sorted keys, integral floats written as integers).

Rules (see CLAUDE.md, "Results database"):
  * a parameter's resolved value is what is stored, so a component whose constructor replaces `None` by a default overrides
    `params()` to report the effective value;
  * a new parameter changes the hash of every agent that uses the component (re-hash from the stored spec JSON);
  * a `type` names one behavior: never reuse a class name for different behavior;
  * only the classes defined in the library modules (LIBRARY_MODULES) can be built from a spec; a class defined elsewhere (a test)
    still has a spec but must be passed to `build` through `extra`.
"""

import functools
import hashlib
import inspect
import json
import numbers

import numpy as np

LIBRARY_MODULES = ("agents", "perception")
COMPONENTS = {}       # class name -> class, for the library's own components


class SpecError(ValueError):
    """A component holds something that cannot be written into a spec (a function, an array...), or a spec cannot be built."""


class Component:
    """Base of everything an agent is made of. Subclasses need no code: their constructor arguments are captured (the outermost
    call, so a subclass that calls `super().__init__` records its own) and reported by `spec()`."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        init = cls.__dict__.get("__init__")
        if init is not None:
            signature = inspect.signature(init)

            @functools.wraps(init)
            def wrapped(self, *args, **kw):
                if "_ctor" not in self.__dict__:
                    bound = signature.bind(self, *args, **kw)
                    bound.apply_defaults()
                    params = dict(bound.arguments)
                    params.pop("self")
                    self.__dict__["_ctor"] = params
                init(self, *args, **kw)

            cls.__init__ = wrapped
        if cls.__module__ in LIBRARY_MODULES:
            if cls.__name__ in COMPONENTS and COMPONENTS[cls.__name__] is not cls:
                raise SpecError(f"two library components are named {cls.__name__}")
            COMPONENTS[cls.__name__] = cls

    def params(self):
        """The resolved constructor arguments (override where the constructor replaces an argument by a default)."""
        return dict(self.__dict__.get("_ctor", {}))

    def spec(self):
        params = self.params()
        if "type" in params:
            raise SpecError(f"{type(self).__name__} has a parameter named 'type', which the spec reserves")
        out = {"type": type(self).__name__}
        for key, value in params.items():
            out[key] = _spec_value(value, f"{type(self).__name__}.{key}")
        return out


def _spec_value(value, where):
    if isinstance(value, Component):
        return value.spec()
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        value = float(value)
        return int(value) if value.is_integer() else value
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_spec_value(v, where) for v in value]
    raise SpecError(f"{where} = {value!r} cannot be written into a spec")


def _normalize(value):
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    return _spec_value(value, "spec")


def canonical_json(spec):
    """Sorted keys, no spaces, numbers by value (10, 10.0 and numpy floats are the same number)."""
    return json.dumps(_normalize(spec), sort_keys=True, separators=(",", ":"))


def spec_hash(spec):
    """The identity of an agent spec: 12 hex characters of the SHA-256 of its canonical JSON."""
    return hashlib.sha256(canonical_json(spec).encode()).hexdigest()[:12]


def build(spec, extra=None):
    """The component (or agent part) described by `spec`. `extra` maps class names to classes that are not in the library."""
    if spec is None or isinstance(spec, (bool, int, float, str)):
        return spec
    if isinstance(spec, list):
        return [build(v, extra) for v in spec]
    if not isinstance(spec, dict) or "type" not in spec:
        raise SpecError(f"{spec!r} is not a component spec")
    name = spec["type"]
    classes = {**COMPONENTS, **(extra or {})}
    if name not in classes:
        raise SpecError(f"unknown component type '{name}' (a class outside {LIBRARY_MODULES} must be passed in `extra`)")
    kwargs = {k: build(v, extra) for k, v in spec.items() if k != "type"}
    return classes[name](**kwargs)


def flatten(spec, prefix=""):
    """{'critic.alpha': 0.5, 'critic.features.length_scale': 0.3, ...}: one entry per parameter, 'type' entries included."""
    out = {}
    for key, value in spec.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, path + "."))
        else:
            out[path] = value
    return out


def labels(specs):
    """A label for each spec in `specs` made of only the fields that differ among them: `alpha=0.2` against `alpha=0.5`, `RBFFeatures`
    against `SSPFeatures`. When a component's `type` differs, its own parameters and subcomponents are left out unless two specs of the
    same type disagree on them (the type says the rest), so a table of unlike agents reads `OracleCritic, FullKnowledge,
    utility=nearest` instead of every field. Types come first. A field
    that is missing from a spec is left out of that label. Identical specs get the label 'same'. A field is named by its last path
    segment when that is unambiguous among the shown fields, else by its full path."""
    flat = [flatten(s) for s in specs]
    differing = sorted({k for f in flat for k in f if len({repr(f.get(k, _MISSING)) for f in flat}) > 1})
    is_type = lambda k: k == "type" or k.endswith(".type")
    parents = [k[:-4] for k in differing if is_type(k)]                    # "critic." for critic.type; "" for a top-level type
    def informative(k):
        # under a component whose type differs, a parameter matters only where two specs of the same type disagree on it
        for p in parents:
            if p and k.startswith(p) and k != p + "type":
                groups = {}
                for f in flat:
                    groups.setdefault(repr(f.get(p + "type")), set()).add(repr(f.get(k, _MISSING)))
                if not any(len(v) > 1 for v in groups.values()):
                    return False
        return True

    keys = [k for k in differing if informative(k)]
    keys.sort(key=lambda k: (not is_type(k), k))
    last = [k.rsplit(".", 1)[-1] for k in keys]
    names = {k: (short if last.count(short) == 1 else k) for k, short in zip(keys, last)}
    out = []
    for f in flat:
        parts = [str(f[k]) if is_type(k) else f"{names[k]}={f[k]}" for k in keys if k in f]
        out.append(", ".join(parts) or "same")
    return out


_MISSING = object()
