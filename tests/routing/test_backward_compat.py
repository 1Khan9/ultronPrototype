"""Backward-compatibility tests for the CodingVoiceController rename.

The class was renamed to CapabilityVoiceController in Foundation Phase 5;
``CodingVoiceController`` is kept as a module-level alias. Existing
imports must keep working unchanged.
"""

from __future__ import annotations

from kenning.coding import CapabilityVoiceController, CodingVoiceController


def test_alias_resolves_to_same_class():
    assert CodingVoiceController is CapabilityVoiceController


def test_existing_import_path_still_works():
    """`from kenning.coding import CodingVoiceController` is still the
    public import for legacy code."""
    from kenning.coding import CodingVoiceController as Imported
    assert Imported is CapabilityVoiceController


def test_isinstance_check_works_through_alias():
    """Code that does `isinstance(obj, CodingVoiceController)` keeps
    working because it's the same class object as the new name."""
    # We can't construct without dependencies, but we can verify the type
    # identity, which is what isinstance ultimately uses.
    assert CodingVoiceController.__name__ == "CapabilityVoiceController"


def test_module_level_re_exports():
    """The package's __all__ must include both names so static analyzers
    flag neither as missing."""
    import kenning.coding as coding_pkg
    assert "CapabilityVoiceController" in coding_pkg.__all__
    assert "CodingVoiceController" in coding_pkg.__all__
