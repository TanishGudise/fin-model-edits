import sys
from pathlib import Path

from verifiers.v1.clients import ModelContext
from verifiers.v1.harness import Harness, HarnessConfig
from verifiers.v1.runtimes import ProgramResult, Runtime
from verifiers.v1.runtimes.subprocess import SubprocessRuntime
from verifiers.v1.trace import Trace

PROGRAM_PATH = Path(__file__).resolve().parent / "program.py"
PROGRAM_SOURCE = PROGRAM_PATH.read_text()


class ClaudeSingleTurnConfig(HarnessConfig):
    pass


class ClaudeSingleTurnHarness(Harness[ClaudeSingleTurnConfig]):
    """The single-turn task over the Anthropic Messages API: the model sees the task prompt and
    answers once, with no tools. Select it with `--harness.id fin_model_edits_claude`
    and point the client at Anthropic (`--client.base-url https://api.anthropic.com
    --client.api-key-var ANTHROPIC_API_KEY`)."""

    APPENDS_SYSTEM_PROMPT = True

    async def _program(self, runtime: Runtime, env: dict[str, str]) -> list[str]:
        # On the local runtime, run with this package's own interpreter: `anthropic` comes from
        # the project lock, so a rollout installs nothing and needs no network except the model
        # API. Container runtimes build the uv script environment instead.
        if isinstance(runtime, SubprocessRuntime):
            return [sys.executable, str(PROGRAM_PATH)]
        return await runtime.prepare_uv_script(PROGRAM_SOURCE, env)

    async def setup(self, runtime: Runtime) -> None:
        await self._program(runtime, self.config.resolved_env)

    async def launch(
        self,
        ctx: ModelContext,
        trace: Trace,
        runtime: Runtime,
        endpoint: str,
        secret: str,
        mcp_urls: dict[str, str],
    ) -> ProgramResult:
        system_prompt, prompt = self.resolve_prompt(trace.task.data)
        args = [
            # The SDK appends /v1/messages, so it gets the interception root.
            f"--base-url={endpoint.removesuffix('/v1')}",
            f"--api-key={secret}",
            f"--model={ctx.model}",
        ]
        if system_prompt:
            args.append(f"--system-prompt={system_prompt}")
        if isinstance(prompt, str):
            args.append(f"--prompt={prompt}")
        env = {**self.config.resolved_env}
        program = await self._program(runtime, env)
        return await runtime.run_program([*program, *args], env)
