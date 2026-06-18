# C3 二进制安装器研究

## 结论

C3 初装界面更适合使用 AArch64 ELF 二进制安装器，而不是普通 shell 脚本。当前项目采用 AGNOS Qt setup installer 模板生成二进制安装器，脚本安装器保留为 SSH 救援/回滚备用。

## `gitop.vip/cp` 的形态

`gitop.vip/cp` 下载到本地后是：

```text
ELF 64-bit LSB executable, ARM aarch64, dynamically linked, interpreter /lib/ld-linux-aarch64.so.1
```

二进制字符串里能看到：

```text
libQt5Widgets.so.5
selfdrive/ui/qt/setup/installer.cc
Installing CarrotPilot
rm -rf /data/tmppilot /data/openpilot
https://jihulab.com/fishop/openpilot.git
git checkout cp
git reset --hard origin/cp
mv /data/tmppilot /data/openpilot
chmod +x /data/continue.sh.new
mv /data/continue.sh.new /data/continue.sh
cd /data/openpilot
exec ./launch_openpilot.sh
```

这说明它是旧 Qt setup installer 形态，核心逻辑是拉取指定仓库和分支，然后写 `/data/continue.sh`。

## 生成方式

社区里常用的做法来自 `sshane/openpilot-installer-generator`：

- 准备一个 `installer_openpilot_agnos` 模板二进制。
- 模板里放入足够长的占位字符串：
  - GitHub repo path 占位
  - branch 占位
  - loading message 占位
- 请求安装链接时，把占位字符串替换成真实仓库、分支和显示文字。
- 返回 `application/octet-stream` 二进制文件。

本项目使用同类方式生成二进制安装器，生成脚本是：

```bash
python3 scripts/personal/build_binary_installer.py \
  --output /tmp/installer_c3_escc
```

默认目标：

```text
repo path: JiangNanGenius/CarrotPilot-C3-ESCC.git
branch: install-c3-escc-test
loading: CarrotPilot-C3-ESCC
```

## 为什么二进制安装器使用分支，不直接使用 tag

旧 Qt installer 会执行类似：

```text
git fetch origin <branch>
git checkout <branch>
git reset --hard origin/<branch>
```

tag 可以被 `git clone -b <tag>` 使用，但 `origin/<tag>` 不是常规远程分支引用。为了避免缓存安装路径或重置步骤失败，二进制安装器必须指向一个真实分支。

本项目约定：

```text
install-c3-escc-test
```

这个分支只作为安装入口指针。每次发布新的受控测试版或稳定版前，先通过 release gate，再把该分支移动到对应提交。Release tag 负责记录不可变版本，例如：

```text
carrotpilot-c3-escc-20260618-test22
```

## 二进制安装器和脚本安装器的区别

二进制安装器：

- 面向 C3 setup/初装界面。
- 形态和 `gitop.vip/cp` 一致，都是 AArch64 ELF。
- 会直接替换 `/data/openpilot`。
- 不适合在普通电脑上运行。
- 不能像 shell 脚本那样灵活写入更多安全参数，除非重新编译源码。

脚本安装器：

- 面向 SSH 维护、救援和回滚。
- 会先备份旧 `/data/openpilot`。
- 会写入首次启动安全参数。
- 不一定能被 C3 setup/初装界面识别。

因此日常安装入口优先提供二进制，脚本作为备用。

## 后续真正自编译路线

如果以后需要把 `AlwaysOffline=1`、`EnableEscc=0`、车型预设或更多安全参数直接写进二进制安装流程，需要恢复并维护 installer 源码，而不是只做占位替换。

可选路线：

- 旧 Qt 路线：基于 `selfdrive/ui/qt/setup/installer.cc`，用 `BUILD_SETUP=1` 和 openpilot Qt/SCons 环境交叉编译 AArch64。
- 新官方路线：基于 `selfdrive/ui/installer/installer.cc`，使用 raylib installer 和 `selfdrive/ui/SConscript` 的 extras 构建路径。

当前先采用模板替换路线，因为它最接近 `gitop.vip/cp` 的实际产物，能最快得到 C3 setup 可识别的安装器。
