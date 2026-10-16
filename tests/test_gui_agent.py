"""T4's agent loop (fin_model_edits/gui/agent.py) against a fake API and a fake desktop: no model calls, no
container."""

from types import SimpleNamespace

from fin_model_edits.gui import agent

PNG = b"\x89PNG\r\n\x1a\n-not-a-real-image"


class FakeDesktop:
    def __init__(self):
        self.acts = []

    def screenshot_png(self):
        return PNG

    def act(self, name, inp):
        if inp.get("coordinate", [0])[0] >= 1280:
            raise ValueError(f"coordinate {inp['coordinate']} is outside the 1280x800 screen")
        self.acts.append((name, inp))
        return [agent._image_block(PNG)] if name == "screenshot" else "OK"


def fake_client(monkeypatch, responses):
    sent = []

    def create(**request):
        sent.append({**request, "messages": [dict(m) for m in request["messages"]]})
        body = responses.pop(0)
        return SimpleNamespace(model_dump=lambda exclude_none=True: body)

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(agent.anthropic, "Anthropic", lambda **kwargs: client)
    return sent


def reply(stop_reason, *calls, text="working"):
    content = [{"type": "thinking", "thinking": "t", "signature": "s"}, {"type": "text", "text": text}]
    content += [
        {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": inp}
        for i, (name, inp) in enumerate(calls)
    ]
    usage = {"input_tokens": 100, "output_tokens": 50}
    return {"content": content, "stop_reason": stop_reason, "usage": usage}


def run(tmp_path, monkeypatch, responses, budget=8.0, max_turns=10, **kwargs):
    sent = fake_client(monkeypatch, responses)
    desktop = FakeDesktop()
    summary = agent.run(
        desktop,
        "task",
        tmp_path,
        model="claude-opus-5-5",
        base_url="http://127.0.0.1:1",
        api_key="x",
        budget=budget,
        max_turns=max_turns,
        **kwargs,
    )
    return summary, desktop, sent


def test_a_truncated_turn_runs_nothing_and_the_trial_goes_on(tmp_path, monkeypatch):
    summary, desktop, sent = run(
        tmp_path,
        monkeypatch,
        [
            # cut off mid-call, as in pilot trial p2: a partial tool call named "computer" with no input
            reply("max_tokens", ("computer", {})),
            reply("max_tokens"),
            reply("tool_use", ("screenshot", {})),
            reply("end_turn", text="done"),
        ],
    )
    assert summary["stop"] == "end_turn" and not summary["harness_stop"]
    assert summary["turns"] == 2 and summary["truncated_turns"] == 2 and summary["requests"] == 4
    assert desktop.acts == [("screenshot", {})]  # the partial call never ran
    # the cut-off turns are dropped: the next request is the first one plus a note on its last user message
    first, second, third = (r["messages"] for r in sent[:3])
    assert len(second) == len(first) == len(third) == 1
    notes = [b["text"] for b in third[0]["content"] if b["type"] == "text"][1:]
    assert len(notes) == 2 and all("was discarded" in n and "2048" in n for n in notes)
    assert all(b.get("name") != "computer" for m in sent[3]["messages"] for b in m["content"])


def test_a_truncated_turn_after_tool_results_gets_its_note_there(tmp_path, monkeypatch):
    summary, _, sent = run(
        tmp_path,
        monkeypatch,
        [reply("tool_use", ("screenshot", {})), reply("max_tokens", ("left_click", {})), reply("end_turn")],
    )
    before, after = sent[1]["messages"], sent[2]["messages"]
    assert len(after) == len(before) == 3 and after[:2] == before[:2]
    assert after[-1]["content"][:-1] == before[-1]["content"]  # the tool results, unchanged
    assert after[-1]["content"][-1]["type"] == "text" and "was discarded" in after[-1]["content"][-1]["text"]
    assert summary["turns"] == 2 and summary["truncated_turns"] == 1  # the end_turn reply is turn 2


def test_a_failed_call_stops_the_rest_of_the_batch(tmp_path, monkeypatch):
    summary, desktop, sent = run(
        tmp_path,
        monkeypatch,
        [
            reply("tool_use", ("left_click", {"coordinate": [5000, 10]}), ("type", {"text": "x"})),
            reply("end_turn"),
        ],
    )
    results = sent[1]["messages"][-1]["content"]
    assert results[0]["is_error"] and "outside" in results[0]["content"]
    assert results[1]["content"] == agent.NOT_EXECUTED
    assert all(r["toolset_name"] == "computer" for r in results)
    assert summary["stop"] == "end_turn"


def test_the_budget_stop_is_a_harness_stop(tmp_path, monkeypatch):
    summary, _, sent = run(tmp_path, monkeypatch, [reply("end_turn")], budget=0.01)
    assert sent == [] and summary["stop"] == "budget" and summary["harness_stop"]


def test_cut_off_turns_dont_use_up_the_turn_limit(tmp_path, monkeypatch):
    shot = ("screenshot", {})
    responses = [reply("max_tokens", shot), reply("tool_use", shot)] * 3
    summary, desktop, sent = run(tmp_path, monkeypatch, responses, max_turns=3)
    assert summary["stop"] == "max_turns" and not summary["harness_stop"]
    assert summary["turns"] == 3 and summary["truncated_turns"] == 3 and len(sent) == 6
    assert len(desktop.acts) == 3


def test_too_many_cut_off_turns_is_a_harness_stop(tmp_path, monkeypatch):
    n = agent.MAX_TRUNCATED + 1
    summary, desktop, sent = run(tmp_path, monkeypatch, [reply("max_tokens")] * n, max_turns=80)
    assert summary["stop"] == "truncations" and summary["harness_stop"]
    assert summary["turns"] == 0 and len(sent) == n and desktop.acts == []


def test_the_first_turn_limit_and_the_power_halt(tmp_path, monkeypatch):
    on_battery = iter([False, True])
    summary, _, sent = run(
        tmp_path,
        monkeypatch,
        [reply("max_tokens", ("screenshot", {}))],
        first_max_tokens=32,
        halt=lambda: next(on_battery),
    )
    assert sent[0]["max_tokens"] == 32
    assert summary["stop"] == "power" and summary["harness_stop"] and summary["turns"] == 0
