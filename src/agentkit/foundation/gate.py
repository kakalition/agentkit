"""Authorization: a :class:`Gate` plus :class:`Policy` classes.

The Gate answers "may this actor do this?" for three kinds of subject — models,
tools, and channels. Abilities are resolved in this order:

1. an explicitly defined closure (``Gate.define("publish", fn)``);
2. a :class:`Policy` registered for the subject (``Gate.policy(Note, NotePolicy)``),
   invoking the method named after the ability;
3. otherwise the request is denied.

    from agentkit import Gate

    class NotePolicy(Policy):
        model = Note
        def update(self, actor, note):
            return note.owner_id == actor.id

    Gate.policy(Note, NotePolicy)
    Gate.allows("update", note, actor=actor)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agentkit.errors import PermissionDenied

__all__ = ["Gate", "GateInspector", "Policy", "Response", "ToolPolicyAdapter"]


def _tool_name(tool: Any) -> str | None:
    if isinstance(tool, str):
        return tool
    name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
    return name if isinstance(name, str) else None


def _decision(policy: Any, name: str) -> str:
    if hasattr(policy, "decision"):
        return str(policy.decision(name))
    if hasattr(policy, "is_allowed"):
        return "allow" if policy.is_allowed(name) else "deny"
    return "allow"


@dataclass
class Response:
    """The result of a Gate check."""

    allowed: bool
    message: str | None = None


class Policy:
    """Base authorization policy.

    Abilities return ``True``/``False`` or ``None`` (no opinion, so the Gate
    falls through). ``before`` runs first and can short-circuit every ability.
    """

    model: Any = None

    def before(self, actor: Any, ability: str, subject: Any = None) -> bool | None:
        return None

    # -- model abilities (Laravel names) --------------------------------
    def viewAny(self, actor: Any, subject: Any = None) -> bool | None:  # noqa: N802
        return None

    def view(self, actor: Any, subject: Any) -> bool | None:
        return None

    def create(self, actor: Any, subject: Any = None) -> bool | None:
        return None

    def update(self, actor: Any, subject: Any) -> bool | None:
        return None

    def delete(self, actor: Any, subject: Any) -> bool | None:
        return None

    def restore(self, actor: Any, subject: Any) -> bool | None:
        return None

    def forceDelete(self, actor: Any, subject: Any) -> bool | None:  # noqa: N802
        return None

    # -- tool / channel abilities ---------------------------------------
    def run(self, actor: Any, tool: Any) -> bool | None:
        return None

    def handle(self, actor: Any, channel: Any) -> bool | None:
        return None


PolicyCallback = Callable[..., bool]


class Gate:
    """Resolve abilities to policies or closures; allow/deny/authorize."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self._abilities: dict[str, PolicyCallback] = {}
        self._policies: dict[Any, Any] = {}
        self._before: list[Callable[[Any, str, Any], bool | None]] = []
        self._tool_policy: Any = None

    # -- tool policy ----------------------------------------------------
    def tool_policy(self, policy: Any) -> Gate:
        """Install a tool-RBAC ``ToolPolicy``; ``allows("run", name)`` consults it."""
        self._tool_policy = policy
        self.policy("tool", ToolPolicyAdapter(policy))
        return self

    def can_run(self, tool: Any, *, actor: Any = None) -> bool:
        """Whether ``tool`` may run under the installed tool policy."""
        if self._tool_policy is None:
            return True
        name = _tool_name(tool)
        if name is None:
            return True
        return _decision(self._tool_policy, name) != "deny"

    # -- registration ---------------------------------------------------
    def define(self, ability: str, callback: PolicyCallback) -> Gate:
        self._abilities[ability] = callback
        return self

    def policy(self, subject: Any, policy: Any = None) -> Gate:
        """Register a policy for a subject (a class, an instance, or a name)."""
        if policy is None:
            return self
        key = subject if isinstance(subject, type) else self._subject_key(subject)
        if isinstance(policy, type):
            model = getattr(policy, "model", None)
            if key is None and model is not None:
                key = model
        self._policies[key] = policy
        return self

    def policies(self, policies: list[Any] | dict[Any, Any]) -> Gate:
        """Register many policies (``{subject: policy}`` or ``[policy, ...]``)."""
        items = policies.items() if isinstance(policies, dict) else [(None, p) for p in policies]
        for subject, policy in items:
            self.policy(subject, policy)
        return self

    def before(self, callback: Callable[[Any, str, Any], bool | None]) -> Gate:
        self._before.append(callback)
        return self

    def has(self, ability: str) -> bool:
        return ability in self._abilities

    # -- checks ---------------------------------------------------------
    def allows(self, ability: str, *arguments: Any, actor: Any = None) -> bool:
        return self._resolve(ability, arguments, actor).allowed

    def denies(self, ability: str, *arguments: Any, actor: Any = None) -> bool:
        return not self.allows(ability, *arguments, actor=actor)

    def any(self, abilities: list[str], *arguments: Any, actor: Any = None) -> bool:
        return any(self.allows(a, *arguments, actor=actor) for a in abilities)

    def none(self, abilities: list[str], *arguments: Any, actor: Any = None) -> bool:
        return not self.any(abilities, *arguments, actor=actor)

    def authorize(self, ability: str, *arguments: Any, actor: Any = None) -> bool:
        """Allow or raise :class:`~agentkit.errors.PermissionDenied`."""
        response = self._resolve(ability, arguments, actor)
        if not response.allowed:
            raise PermissionDenied(
                response.message or f"not authorized to {ability}",
                detail={"ability": ability},
            )
        return True

    def inspect(self, ability: str, *arguments: Any, actor: Any = None) -> Response:
        return self._resolve(ability, arguments, actor)

    def for_user(self, actor: Any) -> GateInspector:
        return GateInspector(self, actor)

    # -- resolution -----------------------------------------------------
    def _subject_key(self, subject: Any) -> Any:
        if subject is None:
            return None
        if isinstance(subject, type):
            return subject
        if isinstance(subject, str):
            return subject
        return type(subject)

    def _policy_for(self, subject: Any) -> Any:
        key = self._subject_key(subject)
        if key in self._policies:
            return self._policies[key]
        if subject is not None and not isinstance(subject, (type, str)):
            for klass in type(subject).__mro__:
                if klass in self._policies:
                    return self._policies[klass]
        return None

    def _resolve(self, ability: str, arguments: tuple[Any, ...], actor: Any) -> Response:
        subject = arguments[0] if arguments else None
        for hook in self._before:
            outcome = hook(actor, ability, subject)
            if outcome is not None:
                return Response(bool(outcome))
        policy = self._policy_for(subject)
        if policy is None and isinstance(subject, str) and ability in {"run", "call", "tool"}:
            policy = self._policies.get("tool")
        if policy is not None:
            instance = policy if not isinstance(policy, type) else policy()
            before = getattr(instance, "before", None)
            if callable(before):
                outcome = before(actor, ability, subject)
                if outcome is not None:
                    return Response(bool(outcome))
            method = self._policy_method(instance, ability)
            if method is not None:
                outcome = method(actor, *arguments)
                if outcome is not None:
                    return Response(
                        bool(outcome),
                        None if outcome else f"policy denied {ability}",
                    )
        callback = self._abilities.get(ability)
        if callback is not None:
            return Response(bool(callback(actor, *arguments)))
        return Response(False, f"no policy or ability defined for {ability}")

    @staticmethod
    def _policy_method(instance: Any, ability: str) -> Any:
        for candidate in (ability, f"can_{ability}"):
            method = getattr(instance, candidate, None)
            if callable(method):
                return method
        return None


class GateInspector:
    """A Gate bound to one actor (``Gate.for_user(actor).allows(...)``)."""

    def __init__(self, gate: Gate, actor: Any) -> None:
        self.gate = gate
        self.actor = actor

    def allows(self, ability: str, *arguments: Any) -> bool:
        return self.gate.allows(ability, *arguments, actor=self.actor)

    def denies(self, ability: str, *arguments: Any) -> bool:
        return self.gate.denies(ability, *arguments, actor=self.actor)

    def authorize(self, ability: str, *arguments: Any) -> bool:
        return self.gate.authorize(ability, *arguments, actor=self.actor)

    def any(self, abilities: list[str], *arguments: Any) -> bool:
        return self.gate.any(abilities, *arguments, actor=self.actor)

    def cannot(self, ability: str, *arguments: Any) -> bool:
        return self.denies(ability, *arguments)

    def can(self, ability: str, *arguments: Any) -> bool:
        return self.allows(ability, *arguments)


class ToolPolicyAdapter(Policy):
    """Adapt a tool-RBAC ``ToolPolicy`` to the Gate (``run``/``call`` abilities)."""

    def __init__(self, policy: Any) -> None:
        self.policy = policy

    def run(self, actor: Any, tool: Any) -> bool | None:
        name = _tool_name(tool)
        if name is None:
            return None
        # approval-gated tools are permitted here (the approval flow gates the call)
        return _decision(self.policy, name) != "deny"
