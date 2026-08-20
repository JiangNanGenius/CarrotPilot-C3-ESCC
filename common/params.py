from openpilot.common.params_pyx import Params, ParamKeyFlag, ParamKeyType, UnknownKeyName

# 扩展 Params 类，加 block 参数（兼容 sunnypilot 最新版）
class ParamsExt(Params):
  def put(self, key, dat, block=False):
    """Write a parameter. block=True waits until it is persisted to disk."""
    if block:
      super().put(key, dat)  # 阻塞写入
    else:
      super().put_nonblocking(key, dat)  # 非阻塞写入

  def put_bool(self, key, val, block=False):
    if block:
      super().put_bool(key, val)
    else:
      super().put_bool_nonblocking(key, val)

# 用扩展类替换原始类
Params = ParamsExt

if __name__ == "__main__":
  import sys
  params = Params()
  key = sys.argv[1]
  assert params.check_key(key), f"unknown param: {key}"
  if len(sys.argv) == 3:
    val = sys.argv[2]
    print(f"SET: {key} = {val}")
    params.put(key, val)
  elif len(sys.argv) == 2:
    print(f"GET: {key} = {params.get(key)}")
