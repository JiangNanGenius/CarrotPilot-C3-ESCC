from openpilot.system.ui.lib.application import text_requires_unifont
from openpilot.selfdrive.assets.fonts.process import FONT_DIR, _char_sets, _gb2312_level1_chars


def _shipped_noto_codepoints() -> set[int]:
  codepoints: set[int] = set()
  for line in (FONT_DIR / "NotoSansSC-Regular.fnt").read_text(encoding="utf-8").splitlines():
    if line.startswith("char id="):
      codepoints.add(int(line.split()[1].split("=", 1)[1]))
  return codepoints


def test_content_driven_font_fallback_detects_supported_cjk_scripts():
  assert text_requires_unifont("当前目标 32")
  assert text_requires_unifont("カーブ")
  assert text_requires_unifont("전방 차량")
  assert text_requires_unifont("ความเร็ว")


def test_content_driven_font_fallback_keeps_inter_for_latin_and_numbers():
  assert not text_requires_unifont("ESCC NORMAL 40 km/h")


def test_cjk_atlas_includes_gb2312_common_wifi_and_road_name_characters():
  common = _gb2312_level1_chars()
  assert len(common) == 3755

  _, unifont_codepoints = _char_sets()
  atlas_chars = set(map(chr, unifont_codepoints))
  assert common <= atlas_chars
  assert set("江南奇才家庭客厅车库光纤无线网络密码悉尼澳洲") <= atlas_chars


def test_shipped_cjk_atlas_matches_generated_character_contract():
  # Checking only _char_sets() can pass while stale .fnt/.png assets are shipped.
  # The descriptor is the runtime source of truth used by raylib on the device.
  _, generated_codepoints = _char_sets()
  assert set(generated_codepoints) == _shipped_noto_codepoints()
