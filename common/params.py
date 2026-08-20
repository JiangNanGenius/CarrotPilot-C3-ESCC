from openpilot.common.params_pyx import Params, ParamKeyFlag, ParamKeyType, UnknownKeyName

# 扩展 Params 类，加 block 参数（兼容 sunnypilot 最新版）。
#
# 这个旧基座用 multiprocessing/fork 启动 manager 子进程。普通写入必须保持
# 旧 API 的同步语义；否则 fork 可能继承正在持有 /data/params/.lock 的异步写
# 线程文件描述符，导致 pandad 和其他进程永久阻塞。只有显式 block=False
# 的调用才走非阻塞路径。
class ParamsExt(Params):
  def put(self, key, dat, block=True):
    """Write a parameter, synchronously unless block=False is explicit."""
    if block:
      super().put(key, dat)  # 阻塞写入
    else:
      super().put_nonblocking(key, dat)  # 非阻塞写入

  def put_bool(self, key, val, block=True):
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
