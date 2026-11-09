"""Client LLM pour une API compatible OpenAI (vLLM, Ollama, ...).       [FOURNI]

Utilisation :

    from rag.src.llm import LLM
    llm = LLM()

    llm.chat([{"role": "user", "content": "Bonjour !"}])          # -> str
    for token in llm.stream(messages):                              # réponse au fil de l'eau
        print(token, end="")

    class Personne(BaseModel):                                      # sortie structurée (JSON)
        nom: str
        age: int
    llm.json([{"role": "user", "content": "Jules a 25 ans."}], Personne)   # -> Personne

    def meteo(ville: str) -> str:                                   # appel d'outils
        '''Donne la météo d'une ville.'''
        return "Il pleut."
    run = llm.run_tools(messages, tools=[meteo])                    # -> ToolRun(text, calls)
"""

from __future__ import annotations

import contextvars
import copy
import inspect
import json
import re
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Literal, TypeVar

import openai
from pydantic import BaseModel

from .config import Settings, load_settings

Message = dict[str, Any]
T = TypeVar("T", bound=BaseModel)

_THINK = re.compile(r"<think>.*?</think>\s*", re.S)

# Appels enregistrés pour l'interface (onglet « Prompt ») : None = pas d'enregistrement
_CALLS: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar("llm_calls", default=None)


def record_calls() -> list[dict[str, Any]]:
    """Enregistre, dans le contexte courant, chaque appel au LLM : {"kind", "messages"}."""
    calls: list[dict[str, Any]] = []
    _CALLS.set(calls)
    return calls


class LLMError(RuntimeError):
    """Erreur de communication avec le serveur LLM."""


@dataclass
class ToolRun:
    """Résultat d'une boucle d'appels d'outils."""

    text: str
    calls: list[dict[str, Any]] = field(default_factory=list)  # [{name, arguments, result}]


class LLM:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self.model = self.settings.llm_model
        self.client = openai.OpenAI(
            base_url=self.settings.api.base_url,
            api_key=self.settings.api.api_key or "EMPTY",
            timeout=self.settings.timeout,
            max_retries=1,
        )

    # ── Appels de base ───────────────────────────────────────────────────────

    def _create(self, messages: list[Message], **kwargs: Any) -> Any:
        calls = _CALLS.get()
        if calls is not None:
            kind = (
                "génération de la réponse" if kwargs.get("stream")
                else "sortie structurée (JSON)" if kwargs.get("response_format")
                else "appel d'outils" if kwargs.get("tools")
                else "chat"
            )
            calls.append({"kind": kind, "messages": copy.deepcopy(messages)})
        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", None) or self.settings.temperature,
            "max_tokens": kwargs.pop("max_tokens", None) or self.settings.max_tokens,
        }
        params.update({k: v for k, v in kwargs.items() if v is not None})
        if self.settings.extra_body:
            params["extra_body"] = {**self.settings.extra_body, **params.get("extra_body", {})}
        try:
            return self.client.chat.completions.create(**params)
        except openai.APIConnectionError as e:
            raise LLMError(
                f"Impossible de joindre l'API LLM ({self.settings.api.base_url}). "
                "Vérifiez la section [api] de config.toml et que le serveur est lancé."
            ) from e
        except openai.NotFoundError as e:
            raise LLMError(
                f"Modèle « {self.model} » inconnu du serveur. "
                "Listez les modèles disponibles avec : rag check"
            ) from e

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Envoie une conversation, renvoie la réponse complète."""
        response = self._create(
            messages, temperature=temperature, max_tokens=max_tokens, response_format=response_format
        )
        return _THINK.sub("", response.choices[0].message.content or "").strip()

    def ask(self, prompt: str, **kwargs: Any) -> str:
        """Raccourci : une seule question, sans historique."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Envoie une conversation, renvoie la réponse morceau par morceau."""
        response = self._create(messages, temperature=temperature, max_tokens=max_tokens, stream=True)
        thinking = False
        for event in response:
            if not event.choices:
                continue
            delta = event.choices[0].delta.content or ""
            # Certains serveurs renvoient la « réflexion » dans le texte : on la masque
            if "<think>" in delta:
                thinking = True
                delta = delta.split("<think>")[0]
            if thinking:
                if "</think>" in delta:
                    thinking = False
                    delta = delta.split("</think>", 1)[1].lstrip()
                else:
                    continue
            if delta:
                yield delta

    # ── Sorties structurées ──────────────────────────────────────────────────

    def json(self, messages: list[Message], schema: type[T], *, retries: int = 1) -> T:
        """Demande une réponse conforme à un modèle Pydantic et la valide."""
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        }
        messages = list(messages)
        error = None
        for _ in range(retries + 1):
            try:
                text = self.chat(messages, response_format=response_format)
            except openai.BadRequestError:  # serveur sans support des schémas JSON
                hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
                messages = messages + [{
                    "role": "system",
                    "content": f"Réponds uniquement avec un objet JSON conforme à ce schéma : {hint}",
                }]
                text = self.chat(messages, response_format={"type": "json_object"})
            try:
                return schema.model_validate_json(_extract_json(text))
            except Exception as e:  # noqa: BLE001
                error = e
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"JSON invalide ({e}). Réponds avec un JSON valide."},
                ]
        raise LLMError(f"Réponse JSON invalide : {error}")

    # ── Appels d'outils ──────────────────────────────────────────────────────

    def run_tools(
        self,
        messages: list[Message],
        tools: list[Callable[..., Any]],
        *,
        max_rounds: int = 5,
    ) -> ToolRun:
        """Laisse le modèle appeler des fonctions Python jusqu'à obtenir une réponse.

        Chaque outil est une fonction annotée dont la docstring décrit l'usage.
        """
        specs = [tool_spec(f) for f in tools]
        by_name = {f.__name__: f for f in tools}
        messages = list(messages)
        calls: list[dict[str, Any]] = []
        for _ in range(max_rounds):
            response = self._create(messages, tools=specs)
            message = response.choices[0].message
            if not message.tool_calls:
                return ToolRun(_THINK.sub("", message.content or "").strip(), calls)
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [tc.model_dump(exclude_none=True) for tc in message.tool_calls],
            })
            for call in message.tool_calls:
                name = call.function.name
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                    result = by_name[name](**arguments)
                except KeyError:
                    arguments, result = {}, f"Erreur : outil inconnu « {name} »."
                except Exception as e:  # noqa: BLE001 - l'erreur est renvoyée au modèle
                    arguments = arguments if "arguments" in locals() else {}
                    result = f"Erreur : {e}"
                calls.append({"name": name, "arguments": arguments, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str),
                })
        messages.append({"role": "user", "content": "Réponds maintenant avec les informations obtenues."})
        return ToolRun(self.chat(messages), calls)

    # ── Divers ───────────────────────────────────────────────────────────────

    def models(self) -> list[str]:
        """Modèles proposés par le serveur."""
        try:
            return sorted(m.id for m in self.client.models.list())
        except openai.APIConnectionError as e:
            raise LLMError(f"Impossible de joindre l'API ({self.settings.api.base_url}).") from e


def _extract_json(text: str) -> str:
    text = text.strip()
    if m := re.search(r"```(?:json)?\s*(.*?)```", text, re.S):
        return m.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=0)
    return text[start:]


def tool_spec(function: Callable[..., Any]) -> dict[str, Any]:
    """Décrit une fonction Python au format « tool » de l'API OpenAI."""
    hints = typing.get_type_hints(function)
    properties, required = {}, []
    for name, parameter in inspect.signature(function).parameters.items():
        properties[name] = _json_type(hints.get(name, str))
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "type": "function",
        "function": {
            "name": function.__name__,
            "description": inspect.getdoc(function) or "",
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def _json_type(annotation: Any) -> dict[str, Any]:
    origin = typing.get_origin(annotation)
    if origin is Literal:
        return {"type": "string", "enum": list(typing.get_args(annotation))}
    if origin in (list, tuple):
        args = typing.get_args(annotation)
        return {"type": "array", "items": _json_type(args[0] if args else str)}
    if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _json_type(args[0]) if args else {"type": "string"}
    return {
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        dict: {"type": "object"},
    }.get(annotation, {"type": "string"})
