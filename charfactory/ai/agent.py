"""Loop do assistente: manda a conversa ao provedor, roda as ferramentas que o modelo pede e
devolve os resultados, até ele responder sem pedir mais nada."""
from __future__ import annotations

from typing import Callable

from . import guide, tools
from .providers import Provider, ProviderError

MAX_STEPS = 40
# a resposta bateu no limite de saída: a última chamada pode ter vindo pela metade
TRUNCATED = {"max_tokens", "length", "MAX_TOKENS"}

SYSTEM = (
    "You are the assistant built into Char Factory, an editor for M.U.G.E.N and Ikemen GO fighting game "
    "characters, and an expert in MUGEN's file formats (DEF, CNS, CMD, AIR, SFF, SND), state controllers, "
    "triggers and move design. You work on the character the user has open through your tools: read "
    "before you change anything, keep the character's own style and numbering, and prefer small, exact "
    "edits to rewriting whole files. After changing states or animations, run validate_character, and "
    "simulate_state to check a move's frame data. Your changes stay in memory and the user can undo each "
    "one with Ctrl+Z; never call save_project unless the user asks to save. Answer in the language the "
    "user writes in, briefly, and say what you changed (state, animation or command numbers). "
    "Each user message starts with an <editor> note from the editor (not typed by the user): the open "
    "character, unsaved changes and what the user is looking at; 'this move' or 'this animation' "
    "means that. "
    + tools.MOVE_RECIPE + "\n\nHow MUGEN works (the mugen_guide topics):\n\n"
    + "\n\n".join(f"## {k}\n{v}" for k, v in guide.TOPICS.items()))


class Agent:
    """Uma conversa. `host.call` roda as ferramentas (na janela, na thread da interface)."""

    def __init__(self, provider: Provider, host: tools.Host, system: str = SYSTEM):
        self.provider = provider
        self.host = host
        self.system = system
        self.messages: list = []
        self.cancelled = False

    def send(self, text: str, on_event: Callable[[str, object], None] = lambda kind, data: None) -> str:
        """Manda uma mensagem do usuário e roda até a resposta final. Eventos: 'text' (str),
        'tool' (Call, antes de rodar), 'result' ((Call, Result)) e 'stopped'."""
        self.provider.add_user(self.messages, text)
        return self.resume(on_event)

    def resume(self, on_event: Callable[[str, object], None] = lambda kind, data: None) -> str:
        """Continua de onde parou (depois de um erro do provedor) sem repetir a mensagem."""
        self.cancelled = False
        catalog = tools.describe()
        final = ""
        for _ in range(MAX_STEPS):
            turn = self.provider.step(self.messages, self.system, catalog)
            if turn.text:
                final = turn.text
                on_event("text", turn.text)
            if not turn.calls:
                return final
            results = []
            for call in turn.calls:
                if self.cancelled:
                    res = tools.Result("cancelled by the user", is_error=True)
                elif turn.stop in TRUNCATED:
                    res = tools.Result("not run: your reply hit the output limit, so this call may be cut "
                                       "short; make smaller changes (one statedef or animation per call)",
                                       is_error=True)
                elif call.bad_args is not None:
                    res = tools.Result(f"arguments are not valid JSON: {call.bad_args[:200]}", is_error=True)
                else:
                    on_event("tool", call)
                    res = self.host.call(call.name, call.args)
                on_event("result", (call, res))
                results.append((call, res))
            self.provider.add_results(self.messages, results)    # toda chamada precisa de resultado
            if self.cancelled:
                on_event("stopped", None)
                return final
        raise ProviderError(f"stopped after {MAX_STEPS} steps without a final answer")
