"""
PatternRegistry: central registry for chart pattern detector plugins.

Usage — registering a new pattern:

    from groups.chart_pattern.registry import PatternRegistry
    from groups.chart_pattern.patterns.base import BasePatternDetector

    @PatternRegistry.register
    class MyNewPattern(BasePatternDetector):
        name = "my_new_pattern"
        hypothesis_refs = ["H1-XXX"]
        ...

Usage — querying the registry:

    # Get a specific pattern class by name or hypothesis ref
    klass = PatternRegistry.get_pattern("double_bottom")    # by name
    klass = PatternRegistry.get_pattern("H1-003")           # by hypothesis ref

    # Iterate all registered hypothesis-ref → class mappings
    for hyp_id, klass in PatternRegistry.get_all_by_hypothesis().items():
        ...

Auto-discovery:

    PatternRegistry.autodiscover()  # imports all non-private modules in patterns/

    After autodiscover(), get_all_by_hypothesis() returns every registered pattern
    class keyed by hypothesis ref.  Modules in patterns/ that use @PatternRegistry.register
    are automatically included; those that don't (e.g. base.py, template.py) are skipped.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Optional

logger = logging.getLogger(__name__)

_PATTERNS_PKG = "groups.chart_pattern.patterns"


class PatternRegistry:
    """
    Singleton class-level registry for BasePatternDetector subclasses.

    State is class-level (shared across all instances and imports).
    Registration is idempotent — re-registering the same class is a no-op.
    """

    # hypothesis_ref → detector class (e.g. "H1-003" → DoubleBottomMachine)
    _by_hypothesis: dict[str, type] = {}
    # pattern name → detector class (e.g. "double_bottom" → DoubleBottomMachine)
    _by_name: dict[str, type] = {}
    # Track whether autodiscover has run to avoid repeated imports
    _discovered: bool = False

    @classmethod
    def register(cls, pattern_class: type) -> type:
        """
        Class decorator that registers a BasePatternDetector subclass.

        Reads ``pattern_class.name`` and ``pattern_class.hypothesis_refs``
        and stores them in the registry.  Designed to be used as a decorator::

            @PatternRegistry.register
            class DoubleBottomMachine(BasePatternDetector):
                name = "double_bottom"
                hypothesis_refs = ["H1-003"]
                ...

        Returns the class unchanged so the decorator is transparent.
        """
        name = getattr(pattern_class, "name", "")
        hypothesis_refs = getattr(pattern_class, "hypothesis_refs", [])

        if name:
            cls._by_name[name] = pattern_class

        for href in (hypothesis_refs or []):
            if href:
                cls._by_hypothesis[href] = pattern_class

        logger.debug(
            "PatternRegistry: registered %s (name=%r, hypothesis_refs=%r)",
            pattern_class.__name__, name, hypothesis_refs,
        )
        return pattern_class

    @classmethod
    def get_all_patterns(cls) -> dict[str, type]:
        """Return all registered patterns keyed by pattern name."""
        return dict(cls._by_name)

    @classmethod
    def get_all_by_hypothesis(cls) -> dict[str, type]:
        """Return all registered patterns keyed by hypothesis ref."""
        return dict(cls._by_hypothesis)

    @classmethod
    def get_pattern(cls, name: str) -> Optional[type]:
        """
        Look up a pattern class by name OR hypothesis ref.

        Checks ``name`` first, then ``hypothesis_ref``.  Returns ``None`` if
        no match is found.

        Args:
            name: Pattern name (e.g. ``"double_bottom"``) or hypothesis ref
                  (e.g. ``"H1-003"``).
        """
        return cls._by_name.get(name) or cls._by_hypothesis.get(name)

    @classmethod
    def autodiscover(cls) -> None:
        """
        Import all non-private modules in the ``patterns/`` package and scan
        them for ``BasePatternDetector`` subclasses.

        Works correctly after a ``_reset()`` even when modules are already
        cached in ``sys.modules``: instead of relying solely on decorator
        side-effects (which only fire on first import), it explicitly scans
        each module's attributes after loading.

        Skips modules starting with ``_`` (e.g. ``__init__.py``) and the
        ``base`` and ``template`` modules (they contain no concrete patterns).

        Safe to call multiple times — subsequent calls are no-ops unless the
        registry was reset between calls.
        """
        if cls._discovered:
            return

        try:
            import sys as _sys
            import groups.chart_pattern.patterns as _pkg
            skip = {"base", "template"}
            for _, module_name, _ in pkgutil.iter_modules(_pkg.__path__):
                if module_name.startswith("_") or module_name in skip:
                    continue
                full_name = f"{_PATTERNS_PKG}.{module_name}"
                try:
                    importlib.import_module(full_name)
                    logger.debug("PatternRegistry: imported %s", full_name)
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        "PatternRegistry: failed to import %s: %s", full_name, exc
                    )
                # Scan the (possibly cached) module for BasePatternDetector subclasses.
                # This handles the case where the registry was cleared after first import —
                # the @register decorator won't fire again but we can still re-register.
                mod = _sys.modules.get(full_name)
                if mod is not None:
                    cls._scan_module(mod)
        except Exception as exc:  # pragma: no cover
            logger.warning("PatternRegistry: autodiscover failed: %s", exc)

        cls._discovered = True

    @classmethod
    def _scan_module(cls, mod) -> None:
        """
        Scan a module for ``BasePatternDetector`` subclasses and register them.

        Uses duck typing: any class with a non-empty ``name`` attribute and a
        non-empty ``hypothesis_refs`` list is treated as a detector plugin.
        Already-registered entries are overwritten, so re-scanning is safe.
        """
        for attr_name in dir(mod):
            if attr_name.startswith("_"):
                continue
            attr = getattr(mod, attr_name, None)
            if not (attr is not None and isinstance(attr, type)):
                continue
            name = getattr(attr, "name", "")
            hrefs = getattr(attr, "hypothesis_refs", [])
            if not name or not hrefs:
                continue
            if name not in cls._by_name:
                cls._by_name[name] = attr
            for href in hrefs:
                if href and href not in cls._by_hypothesis:
                    cls._by_hypothesis[href] = attr

    @classmethod
    def _reset(cls) -> None:
        """
        Reset registry state.  Used in tests only — not part of public API.
        """
        cls._by_hypothesis.clear()
        cls._by_name.clear()
        cls._discovered = False
