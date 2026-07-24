from coursekit import hardware


def _stub(monkeypatch, models, available):
    monkeypatch.setattr(hardware, "list_lm_models", lambda: models)
    monkeypatch.setattr(hardware, "get_memory_info", lambda: (32.0, available))
    monkeypatch.setattr(hardware, "loaded_model_keys", lambda: set())


def test_fits_when_under_budget(monkeypatch):
    _stub(monkeypatch, [{"modelKey": "gemma", "sizeBytes": 14 * 1024**3}], available=30.0)
    verdict, msg = hardware.check_fit("gemma")
    assert verdict is True
    assert "fits" in msg


def test_does_not_fit_when_over_budget(monkeypatch):
    # 19 GB model, 21 GB available → budget 14.7 GB → too big. The real 35b-a3b case.
    _stub(monkeypatch, [{"modelKey": "big", "sizeBytes": 19 * 1024**3}], available=21.0)
    verdict, msg = hardware.check_fit("big")
    assert verdict is False
    assert "may fail to load" in msg
    assert "19" in msg and "GB" in msg


def test_unknown_when_model_not_in_catalog(monkeypatch):
    _stub(monkeypatch, [{"modelKey": "other", "sizeBytes": 1}], available=30.0)
    verdict, msg = hardware.check_fit("missing")
    assert verdict is None
    assert "could not find" in msg


def test_unknown_when_ram_unreadable(monkeypatch):
    monkeypatch.setattr(hardware, "list_lm_models",
                        lambda: [{"modelKey": "m", "sizeBytes": 1024**3}])
    monkeypatch.setattr(hardware, "get_memory_info", lambda: (None, None))
    monkeypatch.setattr(hardware, "loaded_model_keys", lambda: set())
    verdict, msg = hardware.check_fit("m")
    assert verdict is None
    assert "could not read available RAM" in msg


def test_list_lm_models_returns_list_when_lms_missing(monkeypatch):
    # No lms binary → empty list, never raises.
    monkeypatch.setattr(hardware.shutil, "which", lambda _: None)
    monkeypatch.setattr(hardware, "_LMS_FALLBACK", "/nonexistent/lms")
    assert hardware.list_lm_models() == []


def test_already_loaded_model_always_fits(monkeypatch):
    # Even with no free RAM, a resident model needs no new allocation.
    monkeypatch.setattr(hardware, "loaded_model_keys", lambda: {"gemma"})
    monkeypatch.setattr(hardware, "get_memory_info", lambda: (32.0, 1.0))
    monkeypatch.setattr(hardware, "list_lm_models",
                        lambda: [{"modelKey": "gemma", "sizeBytes": 15 * 1024**3}])
    verdict, msg = hardware.check_fit("gemma")
    assert verdict is True
    assert "already loaded" in msg


# ------------------------------------------- fit-checking via the provider

def test_local_provider_delegates_to_the_ram_check(monkeypatch):
    from coursekit.providers import OpenAICompatProvider
    _stub(monkeypatch, [{"modelKey": "big", "sizeBytes": 19 * 1024**3}], available=21.0)
    p = OpenAICompatProvider(client=object(), is_local=True)
    verdict, msg = p.check_fit("big")
    assert verdict is False and "may fail to load" in msg


def test_hosted_provider_reports_unknown_not_a_local_ram_verdict(monkeypatch):
    """A cloud endpoint has no local RAM budget — measuring the caller's machine and
    warning about it would be actively misleading."""
    from coursekit.providers import OpenAICompatProvider
    _stub(monkeypatch, [{"modelKey": "gpt", "sizeBytes": 500 * 1024**3}], available=1.0)
    p = OpenAICompatProvider(client=object(), is_local=False)
    assert p.check_fit("gpt") == (None, "")


def test_base_provider_default_is_unknown():
    from coursekit.providers.base import Provider
    class _Bare(Provider):
        def chat_with_tools(self, **kw): ...
        def append_assistant(self, messages, reply): ...
        def append_tool_results(self, messages, results): ...
    assert _Bare().check_fit("anything") == (None, "")
