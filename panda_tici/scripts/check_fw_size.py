#!/usr/bin/env python3
import subprocess
import sys
from collections import defaultdict


def check_space(file, mcu):
  MCUS = {
    "H7": {
      ".flash": 1024*1024, # FLASH
      ".dtcmram": 128*1024, # DTCMRAM
      ".itcmram": 64*1024, # ITCMRAM
      ".axisram": 320*1024, # AXI SRAM
      ".sram12": 32*1024, # SRAM1(16kb) + SRAM2(16kb)
      ".sram4": 16*1024, # SRAM4
      ".backup_sram": 4*1024, # SRAM4
    },
    "F4": {
      ".flash": 1024*1024, # FLASH
      ".dtcmram": 256*1024, # RAM
      ".sram2": 64*1024, # RAM2
    },
  }
  IGNORE_LIST = [
    ".ARM.attributes",
    ".comment",
    ".debug_line",
    ".debug_info",
    ".debug_abbrev",
    ".debug_aranges",
    ".debug_str",
    ".debug_ranges",
    ".debug_loc",
    ".debug_frame",
    ".debug_line_str",
    ".debug_rnglists",
    ".debug_loclists",
  ]
  FLASH = [
    ".isr_vector",
    ".text",
    ".rodata",
    ".data"
  ]
  RAM = [
    ".data",
    ".bss",
    "._user_heap_stack" # _user_heap_stack considered free?
  ]

  result = {}
  sections = {}
  calcs = defaultdict(int)
  failures = []

  output = subprocess.check_output(["arm-none-eabi-size", "-x", "--format=sysv", file], text=True)

  for row in output.split('\n'):
    pop = False
    line = row.split()
    if len(line) == 3 and line[0].startswith('.'):
      if line[0] in IGNORE_LIST:
        continue
      sections[line[0]] = (int(line[1], 16), int(line[2], 16))
      result[line[0]] = [line[1], line[2]]
      if line[0] in FLASH:
        calcs[".flash"] += int(line[1], 16)
        pop = True
      if line[0] in RAM:
        calcs[".dtcmram"] += int(line[1], 16)
        pop = True
      if pop:
        result.pop(line[0])

  if len(result):
    for line in result:
      calcs[line] += int(result[line][0], 16)

  print(f"=======SUMMARY FOR {mcu} FILE {file}=======")
  for line in calcs:
    if line in MCUS[mcu]:
      used_percent = (100 - (MCUS[mcu][line] - calcs[line]) / MCUS[mcu][line] * 100)
      print(f"SECTION: {line} size: {MCUS[mcu][line]} USED: {calcs[line]}({used_percent:.2f}%) FREE: {MCUS[mcu][line] - calcs[line]}")
      if calcs[line] > MCUS[mcu][line]:
        failures.append(f"{line} exceeds its {MCUS[mcu][line]} byte bank")
    else:
      print(line, calcs[line])

  if mcu == "F4":
    data_size, data_addr = sections.get(".data", (0, 0x20000000))
    bss_size, bss_addr = sections.get(".bss", (0, data_addr + data_size))
    static_end = max(data_addr + data_size, bss_addr + bss_size)
    boot_mailbox = 0x2001FFFC
    stack_top = 0x20040000
    stack_guard = 0x4000
    if static_end > boot_mailbox:
      failures.append(f"data/BSS end 0x{static_end:x} overlaps boot mailbox 0x{boot_mailbox:x}")
    if static_end + stack_guard > stack_top:
      failures.append(f"data/BSS leaves less than {stack_guard} bytes below stack top")

    if ".sram2" in sections:
      sram2_size, sram2_addr = sections[".sram2"]
      if sram2_addr != 0x20040000 or sram2_size > 64*1024:
        failures.append(f".sram2 has invalid range 0x{sram2_addr:x}+0x{sram2_size:x}")
    elif "bootstub" not in file:
      failures.append("F4 application is missing its SRAM2 CAN RX queue")

  for failure in failures:
    print(f"ERROR: {failure}")
  print()
  return not failures


if __name__ == "__main__":
  checks = (
    ("../board/obj/bootstub.panda_h7.elf", "H7"),
    ("../board/obj/panda_h7.elf", "H7"),
    ("../board/obj/bootstub.panda.elf", "F4"),
    ("../board/obj/panda.elf", "F4"),
    ("../board/jungle/obj/bootstub.panda_jungle.elf", "F4"),
    ("../board/jungle/obj/panda_jungle.elf", "F4"),
    ("../board/jungle/obj/bootstub.panda_jungle_h7.elf", "H7"),
    ("../board/jungle/obj/panda_jungle_h7.elf", "H7"),
  )
  results = [check_space(file, mcu) for file, mcu in checks]
  sys.exit(0 if all(results) else 1)
