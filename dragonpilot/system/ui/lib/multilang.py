from openpilot.system.ui.lib.multilang import (
  multilang as base_multilang,
  load_translations,
  TRANSLATIONS_DIR,
  tr_noop,
)


class DpMultilang:
  """Wrapper that syncs with base multilang and adds dragonpilot translations."""

  def __init__(self):
    self._dragon_translations: dict[str, str] = {}
    self._dragon_plurals: dict[str, list[str]] = {}
    self._loaded_language: str = ""

  @property
  def languages(self):
    """Delegate to base multilang."""
    return base_multilang.languages

  @property
  def language(self):
    """Delegate to base multilang."""
    return base_multilang.language

  def _ensure_loaded(self):
    """Reload dragon translations if base language changed."""
    current_lang = base_multilang.language
    if current_lang != self._loaded_language:
      self._loaded_language = current_lang
      try:
        po_path = TRANSLATIONS_DIR.joinpath(f'dragonpilot_{current_lang}.po')
        self._dragon_translations, self._dragon_plurals = load_translations(po_path)
      except FileNotFoundError:
        self._dragon_translations = {}
        self._dragon_plurals = {}

  def tr(self, text: str) -> str:
    self._ensure_loaded()
    result = self._dragon_translations.get(text, text)
    return result if result != text else base_multilang.tr(text)

  def trn(self, singular: str, plural: str, n: int) -> str:
    self._ensure_loaded()
    if singular in self._dragon_plurals:
      idx = base_multilang._plural_selector(n)  # noqa — same plural selector
      forms = self._dragon_plurals[singular]
      if idx < len(forms) and forms[idx]:
        return forms[idx]
    return base_multilang.trn(singular, plural, n)


multilang = DpMultilang()

tr, trn = multilang.tr, multilang.trn

__all__ = ['multilang', 'tr', 'trn', 'tr_noop', 'TRANSLATIONS_DIR']
