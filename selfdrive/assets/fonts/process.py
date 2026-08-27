#!/usr/bin/env python3
from pathlib import Path
import argparse
import json

import pyray as rl

FONT_DIR = Path(__file__).resolve().parent
SELFDRIVE_DIR = FONT_DIR.parents[1]
TRANSLATIONS_DIR = SELFDRIVE_DIR / "ui" / "translations"
LANGUAGES_FILE = TRANSLATIONS_DIR / "languages.json"

GLYPH_PADDING = 6
EXTRA_CHARS = "–‑✓×°§•X⚙✕◀▶✔⌫⇧␣○●↳çêüñ–‑✓×°§•€£¥"

# 常用中文字符（驾驶/车辆/设置相关）
COMMON_CHINESE = (
  "的一是不了在人有我他这上们来至大时年个出会可下以说地多你要去那看小想于和之国着没好过天学都么现能成"
  "中为动面发事定还点其些理实社认义前料明日起正新最开已关因为问题常入同业方法表然电全济需军无"
  "它么现像由远尔色太究办接难称权度往物思使界么带世际或空再除科确并院系果期志变界候由当白术内"
  "且利管济制统解政思意取则号名计次选做用效目准平公利展品门四五百六七八九十百千万亿零"
  "上下左右前后内外高低大小多少长短新旧好坏快慢强弱轻重难易"
  "车辆驾驶速度控制距离时间方向转向加速减速刹车油门巡航跟车车道保持辅助"
  "设置系统设备状态版本温度内存存储风扇网络连接在线离线待机行车"
  "限速导航地图摄像头雷达视觉模型预测红绿灯停车起步转弯变道超车"
  "安全警告提示错误故障正常良好一般较差危险紧急"
  "开启关闭启用禁用允许禁止确认取消保存恢复默认自定义"
  "增加减少调整修改删除添加选择切换显示隐藏展开收起"
  "最大最小较高较低较快较慢较强较弱较强较弱"
  "今天明天昨天现在刚才即将已经曾经正在将要"
  "公里米厘米毫米小时分钟秒天周月年"
  "百分之零点一二三四五六七八九十"
)

UNIFONT_LANGUAGES = {"th", "zh-CHT", "zh-CHS", "ko", "ja"}


def _gb2312_level1_chars() -> set[str]:
  """Return GB2312's 3,755 first-level commonly used Han characters."""
  chars: set[str] = set()
  for high_byte in range(0xB0, 0xD8):
    for low_byte in range(0xA1, 0xFF):
      try:
        char = bytes((high_byte, low_byte)).decode("gb2312")
      except UnicodeDecodeError:
        continue
      if len(char) == 1:
        chars.add(char)
  return chars


def _languages():
  if not LANGUAGES_FILE.exists():
    return {}
  with LANGUAGES_FILE.open(encoding="utf-8") as f:
    return json.load(f)


def _char_sets():
  base = set(map(chr, range(32, 127))) | set(EXTRA_CHARS)
  # Include the standardized GB2312 level-1 common set so user-provided text
  # such as Wi-Fi SSIDs, road names and device names does not render as boxes.
  unifont = set(base) | set(COMMON_CHINESE) | _gb2312_level1_chars()

  for language, code in _languages().items():
    unifont.update(language)
    po_path = TRANSLATIONS_DIR / f"app_{code}.po"
    try:
      chars = set(po_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
      continue
    (unifont if code in UNIFONT_LANGUAGES else base).update(chars)

  return tuple(sorted(ord(c) for c in base)), tuple(sorted(ord(c) for c in unifont))


def _glyph_metrics(glyphs, rects, codepoints):
  entries = []
  min_offset_y, max_extent = None, 0
  for idx, codepoint in enumerate(codepoints):
    glyph = glyphs[idx]
    rect = rects[idx]
    width = int(round(rect.width))
    height = int(round(rect.height))
    offset_y = int(round(glyph.offsetY))
    min_offset_y = offset_y if min_offset_y is None else min(min_offset_y, offset_y)
    max_extent = max(max_extent, offset_y + height)
    entries.append({
      "id": codepoint,
      "x": int(round(rect.x)),
      "y": int(round(rect.y)),
      "width": width,
      "height": height,
      "xoffset": int(round(glyph.offsetX)),
      "yoffset": offset_y,
      "xadvance": int(round(glyph.advanceX)),
    })

  if min_offset_y is None:
    raise RuntimeError("No glyphs were generated")

  line_height = int(round(max_extent - min_offset_y))
  base = int(round(max_extent))
  return entries, line_height, base


def _write_bmfont(path: Path, font_size: int, face: str, atlas_name: str, line_height: int, base: int, atlas_size, entries):
  # TODO: why doesn't raylib calculate these metrics correctly?
  if line_height != font_size:
    print("using font size for line height", atlas_name)
    line_height = font_size
  lines = [
    f"info face=\"{face}\" size=-{font_size} bold=0 italic=0 charset=\"\" unicode=1 stretchH=100 smooth=0 aa=1 padding=0,0,0,0 spacing=0,0 outline=0",
    f"common lineHeight={line_height} base={base} scaleW={atlas_size[0]} scaleH={atlas_size[1]} pages=1 packed=0 alphaChnl=0 redChnl=4 greenChnl=4 blueChnl=4",
    f"page id=0 file=\"{atlas_name}\"",
    f"chars count={len(entries)}",
  ]
  for entry in entries:
    lines.append(
      ("char id={id:<4} x={x:<5} y={y:<5} width={width:<5} height={height:<5} " +
       "xoffset={xoffset:<5} yoffset={yoffset:<5} xadvance={xadvance:<5} page=0  chnl=15").format(**entry)
    )
  path.write_text("\n".join(lines) + "\n")


def _process_font(font_path: Path, codepoints: tuple[int, ...]):
  print(f"Processing {font_path.name}...")

  font_size = {
    "unifont.otf": 16,  # unifont is only 16x8 or 16x16 pixels per glyph
    # 36 px stays crisp for the HUD/settings CJK roles while keeping the 3,755
    # common-character atlas within the C3's texture-memory budget.
    "NotoSansSC-Regular.otf": 36,
  }.get(font_path.name, 200)
  glyph_padding = 2 if font_path.name == "NotoSansSC-Regular.otf" else GLYPH_PADDING

  data = font_path.read_bytes()
  file_buf = rl.ffi.new("unsigned char[]", data)
  cp_buffer = rl.ffi.new("int[]", codepoints)
  cp_ptr = rl.ffi.cast("int *", cp_buffer)
  glyphs = rl.load_font_data(rl.ffi.cast("unsigned char *", file_buf), len(data), font_size, cp_ptr, len(codepoints), rl.FontType.FONT_DEFAULT)
  if glyphs == rl.ffi.NULL:
    raise RuntimeError("raylib failed to load font data")

  rects_ptr = rl.ffi.new("Rectangle **")
  image = rl.gen_image_font_atlas(glyphs, rects_ptr, len(codepoints), font_size, glyph_padding, 0)
  if image.width == 0 or image.height == 0:
    raise RuntimeError("raylib returned an empty atlas")

  rects = rects_ptr[0]
  atlas_name = f"{font_path.stem}.png"
  atlas_path = FONT_DIR / atlas_name
  entries, line_height, base = _glyph_metrics(glyphs, rects, codepoints)

  if not rl.export_image(image, atlas_path.as_posix()):
    raise RuntimeError("Failed to export atlas image")

  _write_bmfont(FONT_DIR / f"{font_path.stem}.fnt", font_size, font_path.stem, atlas_name, line_height, base, (image.width, image.height), entries)


def main(font_names: tuple[str, ...] = ()):
  base_cp, unifont_cp = _char_sets()
  fonts = sorted(FONT_DIR.glob("*.ttf")) + sorted(FONT_DIR.glob("*.otf"))
  if font_names:
    requested = set(font_names)
    fonts = [font for font in fonts if font.name in requested]
    missing = requested - {font.name for font in fonts}
    if missing:
      raise FileNotFoundError(f"Unknown font(s): {', '.join(sorted(missing))}")
  for font in fonts:
    if "emoji" in font.name.lower():
      continue
    glyphs = unifont_cp if (font.stem.lower().startswith("unifont") or "notosanssc" in font.stem.lower()) else base_cp
    _process_font(font, glyphs)
  return 0


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("fonts", nargs="*", help="Optional font filenames to rebuild")
  args = parser.parse_args()
  raise SystemExit(main(tuple(args.fonts)))
