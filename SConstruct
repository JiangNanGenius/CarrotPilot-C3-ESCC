import os
import json
import subprocess
import sys
import sysconfig
import platform
import shlex
import importlib
import importlib.metadata
import importlib.util
import tomllib
from types import SimpleNamespace
import numpy as np

import SCons.Errors
from SCons.Defaults import _stripixes

COMMA_HARDWARE = os.path.isfile('/AGNOS')

SCons.Warnings.warningAsException(True)

Decider('MD5-timestamp')

SetOption('num_jobs', max(1, int(os.cpu_count()/(1 if "CI" in os.environ else 2))))

AddOption('--ccflags', action='store', type='string', default='', help='pass arbitrary flags over the command line')
AddOption('--verbose', action='store_true', default=False, help='show full build commands')
AddOption('--pandad-only', action='store_true', default=False,
          help='build cereal, messaging, common, and pandad without unrelated model/UI targets')
release = not os.path.exists(File('#.gitattributes').abspath) # file absent on release branch, see release_files.py
AddOption('--minimal',
          action='store_false',
          dest='extras',
          default=(not COMMA_HARDWARE and not release),
          help='the minimum build to run openpilot. no tests, tools, etc.')

submodule_python_paths = [
  Dir("#").abspath,
  Dir("#msgq_repo").abspath,
  Dir("#opendbc_repo").abspath,
  Dir("#rednose_repo").abspath,
  Dir("#teleoprtc_repo").abspath,
  Dir("#tinygrad_repo").abspath,
]
for p in reversed(submodule_python_paths):
  if p not in sys.path:
    sys.path.insert(0, p)

if external_pythonpath := os.environ.get("PYTHONPATH"):
  submodule_python_paths += [p for p in external_pythonpath.split(os.pathsep) if p and p not in submodule_python_paths]

# Detect platform
arch = subprocess.check_output(["uname", "-m"], encoding='utf8').rstrip()
if platform.system() == "Darwin":
  arch = "Darwin"
elif arch == "aarch64" and COMMA_HARDWARE:
  arch = "comma_arm64"
assert arch in [
  "comma_arm64",  # linux comma hardware (AGNOS) arm64
  "aarch64",      # linux pc arm64
  "x86_64",       # linux pc x64
  "Darwin",       # macOS arm64 (x86 not supported)
]

PANDAD_ONLY = GetOption('pandad_only')
C3_BUILD_DEPS_DIR = "/data/c3-build-deps"
FULL_BUILD_PKG_NAMES = ('acados', 'capnproto', 'eigen', 'ffmpeg', 'json11', 'libjpeg', 'libyuv', 'ncurses', 'zeromq', 'zstd')
C3_BUILD_DEPS_CANDIDATE = (
  COMMA_HARDWARE and arch == "comma_arm64" and not PANDAD_ONLY and os.path.isdir(C3_BUILD_DEPS_DIR)
)
C3_FULL_BUILD_DEPS = C3_BUILD_DEPS_CANDIDATE and any(
  importlib.util.find_spec(name) is None for name in FULL_BUILD_PKG_NAMES
)
if C3_FULL_BUILD_DEPS:
  # The read-only AGNOS root intentionally has no room for build wrappers.
  # Keep the lockfile-pinned ARM64 packages on /data so full rebuilds also work
  # offline after source-only deployments.
  expected_root = os.path.realpath(C3_BUILD_DEPS_DIR)
  sys.path[:] = [p for p in sys.path if os.path.realpath(p or os.curdir) != expected_root]
  sys.path.insert(0, C3_BUILD_DEPS_DIR)
  submodule_python_paths = [
    C3_BUILD_DEPS_DIR,
    *[p for p in submodule_python_paths if os.path.realpath(p) != expected_root],
  ]

pkg_names = ['capnproto', 'libusb', 'ncurses', 'zeromq', 'zstd'] if PANDAD_ONLY else \
            list(FULL_BUILD_PKG_NAMES)

# Production C3 images carry the native pandad headers and shared libraries,
# but intentionally omit comma's Python dependency-wrapper packages. Keep the
# full build hermetic; only the explicitly scoped device-native pandad build may
# use the matching AGNOS system paths when those wrappers are unavailable.
PANDAD_ONLY_SYSTEM_DEPS = {
  'capnproto': ('/usr/local/include', '/usr/local/lib'),
  'libusb': ('/usr/include/libusb-1.0', '/usr/lib/aarch64-linux-gnu'),
  'ncurses': ('/usr/include', '/usr/lib/aarch64-linux-gnu'),
  'zeromq': ('/usr/include', '/usr/lib/aarch64-linux-gnu'),
  'zstd': ('/usr/include', '/usr/lib/aarch64-linux-gnu'),
}

def load_build_package(name):
  try:
    return importlib.import_module(name)
  except ModuleNotFoundError as exc:
    if COMMA_HARDWARE and arch == "comma_arm64" and not PANDAD_ONLY and exc.name == name:
      raise SCons.Errors.UserError(
        f"Missing C3 full-build dependency '{name}'; expected lockfile-pinned wrappers in {C3_BUILD_DEPS_DIR}"
      ) from exc
    if not (PANDAD_ONLY and COMMA_HARDWARE and exc.name == name):
      raise
    include_dir, lib_dir = PANDAD_ONLY_SYSTEM_DEPS[name]
    if not os.path.isdir(include_dir) or not os.path.isdir(lib_dir):
      raise SCons.Errors.UserError(f"Missing C3 system dependency paths for {name}: {include_dir}, {lib_dir}") from exc
    return SimpleNamespace(DIR=os.path.dirname(include_dir), INCLUDE_DIR=include_dir, LIB_DIR=lib_dir)

pkgs = [load_build_package(name) for name in pkg_names]
acados = None if PANDAD_ONLY else pkgs[pkg_names.index('acados')]
capnproto = pkgs[pkg_names.index('capnproto')]
ffmpeg = None if PANDAD_ONLY else pkgs[pkg_names.index('ffmpeg')]
if C3_FULL_BUILD_DEPS:
  def require_bundle_path(name, label, path, *, executable=False):
    real_path = os.path.realpath(path)
    if os.path.commonpath([expected_root, real_path]) != expected_root:
      raise SCons.Errors.UserError(f"C3 build dependency '{name}' has external {label}: {path}")
    if not os.path.isfile(path):
      raise SCons.Errors.UserError(f"C3 build dependency '{name}' is missing {label}: {path}")
    if executable and not os.access(path, os.X_OK):
      raise SCons.Errors.UserError(f"C3 build dependency '{name}' has non-executable {label}: {path}")

  with open(File('#uv.lock').abspath, 'rb') as lock_file:
    lock_packages = {package['name']: package for package in tomllib.load(lock_file)['package']}

  for name, package in zip(pkg_names, pkgs, strict=True):
    package_file = os.path.realpath(package.__file__)
    if os.path.commonpath([expected_root, package_file]) != expected_root:
      raise SCons.Errors.UserError(f"C3 build dependency '{name}' was loaded outside {C3_BUILD_DEPS_DIR}: {package_file}")
    for attr in ("DIR", "INCLUDE_DIR", "LIB_DIR"):
      path = getattr(package, attr, None)
      if not path or not os.path.isdir(path):
        raise SCons.Errors.UserError(f"Invalid C3 build dependency '{name}': {attr}={path}")
      if os.path.commonpath([expected_root, os.path.realpath(path)]) != expected_root:
        raise SCons.Errors.UserError(f"C3 build dependency '{name}' mixes an external {attr}: {path}")

    locked_package = lock_packages[name]
    locked_version = locked_package['version']
    locked_git = locked_package['source']['git']
    locked_commit = locked_git.rsplit('#', 1)[-1]
    distribution = importlib.metadata.distribution(name)
    distribution_root = os.path.realpath(distribution.locate_file(''))
    if os.path.commonpath([expected_root, distribution_root]) != expected_root:
      raise SCons.Errors.UserError(f"C3 build dependency '{name}' metadata was loaded outside {C3_BUILD_DEPS_DIR}")
    direct_url_text = distribution.read_text('direct_url.json')
    direct_url = json.loads(direct_url_text) if direct_url_text else {}
    installed_commit = direct_url.get('vcs_info', {}).get('commit_id')
    if distribution.version != locked_version or installed_commit != locked_commit:
      raise SCons.Errors.UserError(
        f"C3 build dependency '{name}' does not match uv.lock: "
        f"version={distribution.version}, commit={installed_commit}"
      )

  required_bundle_files = {
    'acados': [
      (acados.INCLUDE_DIR, 'acados_c/ocp_nlp_interface.h'),
      (acados.INCLUDE_DIR, 'blasfeo/include/blasfeo_d_aux.h'),
      (acados.INCLUDE_DIR, 'hpipm/include/hpipm_d_ocp_qp.h'),
      (acados.LIB_DIR, 'libacados.so'),
      (acados.LIB_DIR, 'libblasfeo.so'),
      (acados.LIB_DIR, 'libhpipm.so'),
      (acados.LIB_DIR, 'libqpOASES_e.so'),
      (acados.LIB_DIR, 'libqpOASES_e.so.3.1'),
      (acados.TEMPLATE_DIR, 'acados_layout.json'),
      (acados.TEMPLATE_DIR, 'acados_ocp_solver_pyx.pyx'),
      (acados.TEMPLATE_DIR, 'acados_solver_common.pxd'),
      *[(acados.TEMPLATE_DIR, f'c_templates_tera/{template}') for template in (
        'CMakeLists.in.txt',
        'Makefile.in',
        'acados_sim_solver.in.c',
        'acados_sim_solver.in.h',
        'acados_sim_solver.in.pxd',
        'acados_solver.in.c',
        'acados_solver.in.h',
        'acados_solver.in.pxd',
        'constraints.in.h',
        'cost.in.h',
        'main.in.c',
        'main_sim.in.c',
        'model.in.h',
      )],
    ],
    'capnproto': [
      (capnproto.INCLUDE_DIR, 'capnp/message.h'),
      (capnproto.LIB_DIR, 'libcapnp.a'),
      (capnproto.LIB_DIR, 'libkj.a'),
    ],
    'eigen': [(pkgs[pkg_names.index('eigen')].INCLUDE_DIR, 'eigen3/Eigen/Core')],
    'ffmpeg': [
      (ffmpeg.INCLUDE_DIR, 'libavcodec/avcodec.h'),
      (ffmpeg.INCLUDE_DIR, 'libavformat/avformat.h'),
      (ffmpeg.INCLUDE_DIR, 'libavutil/avutil.h'),
      (ffmpeg.INCLUDE_DIR, 'libswresample/swresample.h'),
      *[(ffmpeg.LIB_DIR, f'lib{lib}.a') for lib in ('avformat', 'avcodec', 'swresample', 'avutil', 'x264', 'z', 'va', 'va-drm', 'drm')],
    ],
    'json11': [(pkgs[pkg_names.index('json11')].INCLUDE_DIR, 'json11/json11.hpp'), (pkgs[pkg_names.index('json11')].LIB_DIR, 'libjson11.a')],
    'libjpeg': [(pkgs[pkg_names.index('libjpeg')].INCLUDE_DIR, 'jpeglib.h'), (pkgs[pkg_names.index('libjpeg')].LIB_DIR, 'libjpeg.a')],
    'libyuv': [(pkgs[pkg_names.index('libyuv')].INCLUDE_DIR, 'libyuv.h'), (pkgs[pkg_names.index('libyuv')].LIB_DIR, 'libyuv.a')],
    'ncurses': [(pkgs[pkg_names.index('ncurses')].INCLUDE_DIR, 'ncurses.h'), (pkgs[pkg_names.index('ncurses')].LIB_DIR, 'libncurses.a')],
    'zeromq': [(pkgs[pkg_names.index('zeromq')].INCLUDE_DIR, 'zmq.h'), (pkgs[pkg_names.index('zeromq')].LIB_DIR, 'libzmq.a')],
    'zstd': [(pkgs[pkg_names.index('zstd')].INCLUDE_DIR, 'zstd.h'), (pkgs[pkg_names.index('zstd')].LIB_DIR, 'libzstd.a')],
  }
  for name, required_files in required_bundle_files.items():
    for base_dir, relative_path in required_files:
      require_bundle_path(name, relative_path, os.path.join(base_dir, relative_path))

  capnp_bin = os.path.join(capnproto.DIR, "bin", "capnp")
  capnpc_bin = os.path.join(capnproto.DIR, "bin", "capnpc")
  capnpc_cpp_bin = os.path.join(capnproto.DIR, "bin", "capnpc-c++")
  for name, path in (("acados", acados.TERA_PATH), ("capnproto", capnp_bin),
                     ("capnproto", capnpc_bin), ("capnproto", capnpc_cpp_bin)):
    require_bundle_path(name, "build tool", path, executable=True)
  capnp_version = subprocess.check_output([capnp_bin, "--version"], text=True).strip()
  if capnp_version != "Cap'n Proto version 1.0.1":
    raise SCons.Errors.UserError(f"C3 Cap'n Proto compiler/header mismatch risk: {capnp_version}")
# Shared package ships .so/.dylib; older device venvs still have static .a only.
# Keep static link deps (x264/z/va/drm) when the installed package is static so
# COMMA_HARDWARE CI works without upgrading the device venv yet.
# TODO: drop the static fallback once device venvs have comma-deps-ffmpeg>=7.1.0.post94
_ffmpeg_lib_names = [] if PANDAD_ONLY else (os.listdir(ffmpeg.LIB_DIR) if os.path.isdir(ffmpeg.LIB_DIR) else [])
ffmpeg_shared = any(
  n.startswith('libavcodec.so') or (n.startswith('libavcodec') and n.endswith('.dylib'))
  for n in _ffmpeg_lib_names
)
ffmpeg_libs = [] if PANDAD_ONLY else ['avformat', 'avcodec', 'swresample', 'avutil']
if not PANDAD_ONLY and not ffmpeg_shared:
  ffmpeg_libs += ['x264', 'z']
  if arch != "Darwin":
    ffmpeg_libs += ['va', 'va-drm', 'drm']
acados_include_dirs = [] if PANDAD_ONLY else [
  acados.INCLUDE_DIR,
  os.path.join(acados.INCLUDE_DIR, "blasfeo", "include"),
  os.path.join(acados.INCLUDE_DIR, "hpipm", "include"),
]


# ***** enforce a whitelist of system libraries *****
# this prevents silently relying on a 3rd party package,
# e.g. apt-installed libusb. all libraries should either
# be distributed with all Linux distros and macOS, or
# vendored in commaai/dependencies.
allowed_system_libs = {
  "EGL", "GLESv2", "GL",
  "Qt5Charts", "Qt5Core", "Qt5Gui", "Qt5Widgets",
  "dl", "drm", "gbm", "m", "pthread",
}

def _resolve_lib(env, name):
  for d in env.Flatten(env.get('LIBPATH', [])):
    p = Dir(str(d)).abspath
    for ext in ('.a', '.so', '.dylib'):
      f = File(os.path.join(p, f'lib{name}{ext}'))
      if f.exists() or f.has_builder():
        return name
  if name in allowed_system_libs:
    return name
  raise SCons.Errors.UserError(f"Unexpected non-vendored library '{name}'")

def _libflags(target, source, env, for_signature):
  libs = []
  lp = env.subst('$LIBLITERALPREFIX')
  for lib in env.Flatten(env.get('LIBS', [])):
    if isinstance(lib, str):
      if os.sep in lib or lib.startswith('#'):
        libs.append(File(lib))
      elif lib.startswith('-') or (lp and lib.startswith(lp)):
        libs.append(lib)
      else:
        libs.append(_resolve_lib(env, lib))
    else:
      libs.append(lib)
  return _stripixes(env['LIBLINKPREFIX'], libs, env['LIBLINKSUFFIX'],
                    env['LIBPREFIXES'], env['LIBSUFFIXES'], env, env['LIBLITERALPREFIX'])

build_path = os.environ['PATH']
if C3_FULL_BUILD_DEPS:
  build_path = os.pathsep.join([
    os.path.join(capnproto.DIR, "bin"),
    os.path.dirname(sys.executable),
    build_path,
  ])

build_env = {
    "PATH": build_path,
    "PYTHONPATH": os.pathsep.join(submodule_python_paths),
}
if not PANDAD_ONLY:
  build_env.update({
    "ACADOS_SOURCE_DIR": acados.DIR,
    "ACADOS_PYTHON_INTERFACE_PATH": acados.TEMPLATE_DIR,
    "TERA_PATH": acados.TERA_PATH,
  })

env = Environment(
  ENV=build_env,
  CCFLAGS=[
    "-g",
    "-fPIC",
    "-pipe",
    "-O2",
    "-Wunused",
    "-Werror",
    "-Wshadow" if arch in ("Darwin", "comma_arm64") else "-Wshadow=local",
    "-Wno-unknown-warning-option",
    "-Wno-inconsistent-missing-override",
    "-Wno-c99-designator",
    "-Wno-reorder-init-list",
    "-Wno-vla-cxx-extension",
  ],
  CFLAGS=["-std=gnu11"],
  CXXFLAGS=["-std=c++1z"],
  CPPPATH=[
    "#openpilot",
    "#msgq_repo",            # #include "msgq/..."
    "#opendbc_repo",         # #include "opendbc/..."
    "#rednose_repo",         # #include "rednose/..."
    "#rednose_repo/rednose", # #include "logger/..." (rednose package root)
    "#cereal/gen/cpp",
    "#third_party/json11" if PANDAD_ONLY else [],
    acados_include_dirs,
    [x.INCLUDE_DIR for x in pkgs],
    "#",
  ],
  LIBPATH=[
    "#openpilot/common",
    "#msgq_repo",
    "#openpilot/selfdrive/pandad",
    "#rednose_repo/rednose/helpers",
    "#third_party/json11" if PANDAD_ONLY else [],
    [x.LIB_DIR for x in pkgs],
  ],
  RPATH=[ffmpeg.LIB_DIR] if ffmpeg_shared and not PANDAD_ONLY else [],
  CYTHONCFILESUFFIX=".cpp",
  COMPILATIONDB_USE_ABSPATH=True,
  REDNOSE_ROOT="#rednose_repo",
  tools=["default", "cython", "compilation_db", "rednose_filter"],
  toolpath=["#msgq_repo/site_scons/site_tools", "#rednose_repo/site_scons/site_tools"],
)
# SCons' Darwin linker tool doesn't define the variables used to expand RPATH.
if arch == "Darwin":
  env["RPATHPREFIX"] = "-Wl,-rpath,"
  env["RPATHSUFFIX"] = ""
  env["_RPATH"] = "${_concat(RPATHPREFIX, RPATH, RPATHSUFFIX, __env__)}"
if arch != "comma_arm64":
  env['_LIBFLAGS'] = _libflags

# Arch-specific flags and paths
if arch == "comma_arm64":
  env["CC"] = "clang"
  env["CXX"] = "clang++"
  env.Append(LIBPATH=[
    "/usr/lib/aarch64-linux-gnu",
  ])
  env.Append(CPPPATH=["#third_party/linux/include"])
  # This C3 release still selects the device HAL with __TICI__. Newer upstream
  # renamed the build target to __COMMA_HARDWARE__, so define both while the
  # migrated tree contains the older hw.h contract. Without this, native
  # services silently use the PC paths (for example ~/.comma/params) on-device.
  arch_flags = ["-D__COMMA_HARDWARE__", "-D__TICI__", "-mcpu=cortex-a57"]
  env.Append(CCFLAGS=arch_flags)
  env.Append(CXXFLAGS=arch_flags)
elif arch == "Darwin":
  env.Append(LIBPATH=[
    "/System/Library/Frameworks/OpenGL.framework/Libraries",
  ])
  env.Append(CCFLAGS=["-DGL_SILENCE_DEPRECATION"])
  env.Append(CXXFLAGS=["-DGL_SILENCE_DEPRECATION"])

_extra_cc = shlex.split(GetOption('ccflags') or '')
if _extra_cc:
  env.Append(CCFLAGS=_extra_cc)

# no --as-needed on mac linker
if arch != "Darwin":
  env.Append(LINKFLAGS=["-Wl,--as-needed", "-Wl,--no-undefined"])

# Shorter build output: show brief descriptions instead of full commands.
# Full command lines are still printed on failure by scons.
if not GetOption('verbose'):
  for action, short in (
    ("CC",     "CC"),
    ("CXX",    "CXX"),
    ("LINK",   "LINK"),
    ("SHCC",   "CC"),
    ("SHCXX",  "CXX"),
    ("SHLINK", "LINK"),
    ("AR",     "AR"),
    ("RANLIB", "RANLIB"),
    ("AS",     "AS"),
  ):
    env[f"{action}COMSTR"] = f"  [{short}] $TARGET"

# ********** Cython build environment **********
envCython = env.Clone()
envCython["CPPPATH"] += [sysconfig.get_paths()['include'], np.get_include()]
envCython["CCFLAGS"] += ["-Wno-#warnings", "-Wno-cpp", "-Wno-shadow", "-Wno-deprecated-declarations"]
envCython["CCFLAGS"].remove("-Werror")

envCython["LIBS"] = []
if arch == "Darwin":
  envCython["LINKFLAGS"] = env["LINKFLAGS"] + ["-bundle", "-undefined", "dynamic_lookup"]
else:
  envCython["LINKFLAGS"] = ["-pthread", "-shared"]

np_version = SCons.Script.Value(np.__version__)
Export('envCython', 'np_version')

Export('env', 'arch', 'acados', 'release', 'ffmpeg_libs')

if PANDAD_ONLY:
  # Release snapshots vendor json11 sources but do not install the dependency
  # package used by current upstream build environments.
  json_env = env.Clone()
  json_env.Append(CCFLAGS=['-Wno-unqualified-std-cast-call'])
  json_env.Library('#third_party/json11/json11', ['#third_party/json11/json11.cpp'])

# Setup cache dir
default_cache_dir = '/data/scons_cache' if arch == "comma_arm64" else '/tmp/scons_cache'
cache_dir = ARGUMENTS.get('cache_dir', default_cache_dir)
cache_size_limit = 4e9 if "CI" in os.environ else 2e9
CacheDir(cache_dir)
Clean(["."], cache_dir)

def prune_cache_dir(target=None, source=None, env=None):
  cache_files = sorted((os.path.join(root, f) for root, _, files in os.walk(cache_dir) for f in files), key=os.path.getmtime)
  cache_size = sum(os.path.getsize(f) for f in cache_files)
  for f in cache_files:
    if cache_size < cache_size_limit:
      break
    cache_size -= os.path.getsize(f)
    os.unlink(f)

# ********** start building stuff **********

# Build common module
SConscript(['openpilot/common/SConscript'])
Import('_common')
common = [_common, 'json11', 'zmq']
Export('common')

# Build messaging (cereal + msgq + socketmaster + their dependencies)
# Enable swaglog include in submodules
env_swaglog = env.Clone()
env_swaglog['CXXFLAGS'].append('-DSWAGLOG="\\"common/swaglog.h\\""')
SConscript(['msgq_repo/SConscript'], exports={'env': env_swaglog})

SConscript(['cereal/SConscript'])

Import('socketmaster', 'msgq')
messaging = [socketmaster, msgq, 'capnp', 'kj',]
Export('messaging')


# Release snapshots vendor Panda firmware and may omit the Panda submodule's
# root SConscript. Build host services regardless; firmware is rebuilt from
# panda_tici/SConstruct in the owned release pipeline.
if os.path.exists('panda/SConscript'):
  SConscript(['panda/SConscript'])

if not GetOption('pandad_only'):
  # Build rednose library
  SConscript(['rednose_repo/rednose/SConscript'])

# Build system services
if not GetOption('pandad_only'):
  SConscript([
    'openpilot/system/loggerd/SConscript',
  ])

if arch == "comma_arm64" and not GetOption('pandad_only'):
  SConscript(['openpilot/system/camerad/SConscript'])

# Build selfdrive
SConscript(['openpilot/selfdrive/pandad/SConscript'])
if not GetOption('pandad_only'):
  SConscript([
    'openpilot/selfdrive/controls/lib/longitudinal_mpc_lib/SConscript',
    'openpilot/selfdrive/locationd/SConscript',
    'openpilot/selfdrive/modeld/SConscript',
    'openpilot/selfdrive/ui/SConscript',
  ])
  SConscript(['openpilot/sunnypilot/SConscript'])

# Build desktop-only tools
if GetOption('extras') and arch != "comma_arm64":
  SConscript([
    'openpilot/tools/replay/SConscript',
    'openpilot/tools/cabana/SConscript',
    'openpilot/tools/jotpluggler/SConscript',
  ])


env.CompilationDatabase('compile_commands.json')

# progress output
def count_scons_nodes(nodes):
  seen = set()
  stack = list(nodes)

  while stack:
    node = stack.pop().disambiguate()
    if node in seen:
      continue
    seen.add(node)
    if hasattr(node, 'has_builder') and node.has_builder():
      build_product_nodes.add(node)
    executor = node.get_executor()
    if executor is not None:
      stack += executor.get_all_prerequisites() + executor.get_all_children()

  return len(seen)

progress_interval = 5
progress_count = 0
build_product_nodes = set()
progress_total = max(1, count_scons_nodes(env.arg2nodes(BUILD_TARGETS or [Dir('.')], env.fs.Entry)))

def progress_function(node):
  global progress_count
  if progress_count >= progress_total:
    return
  progress_count = min(progress_count + progress_interval, progress_total)
  progress = round(100. * progress_count / progress_total, 1)
  sys.stderr.write("\rBuilding: %5.1f%%" % progress if sys.stderr.isatty() else "progress: %.1f\n" % progress)
  if progress == 100. and sys.stderr.isatty():
    sys.stderr.write("\n")
  sys.stderr.flush()

Progress(progress_function, interval=progress_interval)
AddPostAction(BUILD_TARGETS or [Dir('.')], prune_cache_dir)

def check_build_product_size(target, source, env):
  limit = 50 * 1024 * 1024  # GitHub max size
  for t in target:
    if hasattr(t, 'isfile') and t.isfile() and (size := os.path.getsize(t.abspath)) > limit:
      raise SCons.Errors.UserError(f"{t} is {size / (1024 * 1024):.1f} MiB, exceeding the {limit / (1024 * 1024):.1f} MiB limit")
if not GetOption('extras'):
  AddPostAction(list(build_product_nodes), Action(check_build_product_size, None))
