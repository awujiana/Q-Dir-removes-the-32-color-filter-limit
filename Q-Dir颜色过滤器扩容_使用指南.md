# Q-Dir 颜色过滤器扩容补丁 · 使用指南

> 面向使用者（不需要懂逆向/x86 汇编）。
> 目标：把 Q-Dir 颜色过滤器（Color Filter）的 **32 条规则上限** 提升到最多 **127 条**。
> 脚本：`qdir_colorfilter_unlimit.py`

---

## 0. 三分钟速查表

| 我想做的事 | 命令 |
| --- | --- |
| 在命令行里看完整指引 | `python qdir_colorfilter_unlimit.py --guide` |
| 看看现在的 Q-Dir 能不能打补丁 | `python qdir_colorfilter_unlimit.py --check` |
| 直接打补丁（不动原文件） | `python qdir_colorfilter_unlimit.py` |
| 打完补丁直接替换原文件 | `python qdir_colorfilter_unlimit.py --in-place` |
| 只想扩到 64 条 | `python qdir_colorfilter_unlimit.py --max 64` |
| 看看脚本找到了哪些 exe | `python qdir_colorfilter_unlimit.py --list` |
| 后悔了，还原 | `python qdir_colorfilter_unlimit.py --restore` |

> 本文所有命令都在脚本所在目录执行，Python 可执行文件请按你自己的环境替换（见第 2 节）。

---

## 1. 这个工具做了什么

Q-Dir 的颜色过滤器在程序里写死了一个上限：最多 32 条规则。超过 32 条后，多出来的规则要么存不进去、要么载入时被截断。

这个脚本做的事：

1. 在 PE 文件里追加一个新区段 `.qdcol`，把原本只有 32×32 字节的颜色规则数组**整体搬迁**过去（原位置后面紧跟着 Q-Dir 自己的对象管理结构，直接扩展会踩坏它）；
2. 把代码中散落的 5 处「上限常量 0x20（32）」改成新上限；
3. 改掉颜色渲染阶段的样式索引守卫（`0..31`）和启动时的清理循环上限；
4. 把 17 处引用该数组的指令重定位到新地址；
5. 写盘后**自动复检**一遍，确认所有改动都落到位。

**限制**

- 只对 **Q-Dir 12.77 x64** 验证过，其它版本几乎一定会因为特征不匹配而拒绝执行（这是保护，不是 bug）。
- 只支持 64 位（AMD64）Q-Dir；32 位版本不适用。
- 上限最大 **127**：代码里用的是 `cmp r32, imm8` 有符号立即数，超过 127 就编码不下了。

---

## 2. 环境准备

### 2.1 Python

需要 Python 3.7 及以上。确认版本：

```bash
python --version
```

> 本项目当前环境里，装了依赖的是系统 Python：`C:\Python314\python.exe`。
> 如果你用其它 Python 报 `[x] 缺少依赖 pefile`，请换成它，或给当前 Python 装依赖（见下）。

### 2.2 依赖

```bash
pip install pefile capstone
```

缺依赖时脚本会直接提示：

```text
[x] 缺少依赖 pefile，请先执行: pip install pefile
```

### 2.3 关闭 Q-Dir

打补丁前**先退出正在运行的 Q-Dir**，否则可能遇到文件占用：

```text
[x] 写入失败: ...（文件被占用或只读，请先关闭 Q-Dir）
```

---

## 3. 它怎么自动找 Q-Dir

不用手工填路径，脚本会自己找。

### 3.1 搜哪些目录

按顺序把这些目录作为搜索根（重复的会自动去重）：

1. 脚本自己所在的目录；
2. 当前工作目录；
3. 脚本目录的**父目录**；
4. 脚本目录和父目录下的常见安装子目录：`Q-Dir`、`Q-Dir_Portable_x64`、`Q-Dir_Portable`、`Q-Dir_x64`、`Q-Dir_x84`、`x64`、`x84`、`bin`、`Portable`；
5. 父目录下**名字里含 `q-dir` 或 `qdir` 的所有子目录**（以及它们的 `Q-Dir` 子目录）。

默认往下最多搜 **3 层**（`--depth` 可调）。

### 3.2 匹配哪些文件名

不区分大小写，匹配 `Q-Dir*.exe` 与 `QDir*.exe`，因此这些都能找到：

```text
Q-Dir.exe      Q-Dir-x64.exe    Q-Dir-x84.exe    Q-Dir-x86.exe
Q-Dir64.exe    Q-Dir_x64.exe    QDir.exe         Q-Dir_12.77.exe  ...
```

小于 200 KB 的 exe 会被忽略（肯定不是 Q-Dir 主程序）。

### 3.3 找到多个时选哪个

按「得分」排序，第一名自动选中：

| 因素 | 影响 |
| --- | --- |
| 文件名是 `Q-Dir.exe` | +100（最高） |
| `Q-Dir-x64.exe` / `Q-Dir-x84.exe` / `Q-Dir64.exe` 等 | +92 ~ +82 |
| 其它 `Q-Dir*.exe` | +50 |
| 名字里含 `patched` / `bak` / `backup` / `备份` / `orig` / `待删除` / `副本` / `copy` 等 | **−45** |
| 文件是 x64 | +30 |
| 文件是 x86 | −25 |
| 目录层级越深 | 每层 −3 |

同分时，修改时间新的优先。

### 3.4 会跳过哪些目录

默认跳过名字里含以下关键字的目录，避免把历史补丁产物搜出来：

```text
备份 / 待删除 / backup / _bak / .git / __pycache__ / node_modules /
$recycle.bin / system volume information / windows / program files / appdata
```

需要连备份一起搜就加 `--include-backup`。

---

## 4. 参数全表

### 4.1 目标定位

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--exe <名字或路径>` | `Q-Dir.exe` | 目标文件名（支持 `*`、`?` 通配符）**或**完整路径。给完整路径时不做搜索，直接使用。 |
| `--dir <目录>` | 无 | 把搜索范围限定在这个目录内（不再自动探测父目录/兄弟目录）。 |
| `--search-dir <目录>` | 无 | **追加**一个搜索根目录，可重复写多次。 |
| `--depth <N>` | `3` | 搜索目录深度。Q-Dir 装在很深的地方时调大，例如 `--depth 5`。 |
| `--pick <N>` | 第 1 个 | 指定使用候选列表中的第 N 个文件（N 见输出里的 `[1]` `[2]`…）。 |
| `--include-backup` | 关闭 | 搜索时不要跳过备份/系统目录。 |
| `--list` | 关闭 | 只列出找到的候选 exe 就退出，不做任何修改。 |

### 4.2 补丁参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--max <32..127>` | `127` | 新的规则上限。 |
| `--out <路径>` | 自动生成 | 指定输出文件路径。 |
| `--in-place` | 关闭 | 就地覆盖目标 exe（会先生成 `.orig` 备份）。不加则输出到 `<name>_patched.exe`，**原文件不动**。 |
| `--no-reloc` | 关闭 | 不搬迁数组（调试用，容量仍受原位置限制，别用于正式补丁）。 |
| `--only <序号>` | 无 | 只改 5 个上限点中的某几个，如 `--only 0,1`（调试用）。 |
| `--force` | 关闭 | 跳过「已打补丁 / 版本不匹配」的预检拦截（**风险自负**）。 |
| `--check` | 关闭 | 只做检查，不修改任何文件。 |
| `--restore` | 关闭 | 用 `<exe>.orig` 还原目标文件。 |

### 4.3 输出控制

| 参数 | 说明 |
| --- | --- |
| `--quiet` | 只输出关键结果与错误，适合脚本调用。 |
| `--guide` | 打印内置完整使用指引（快速开始 / 搜索规则 / 场景 / 退出码 / FAQ）后退出，不联网也能看。 |
| `--color` / `--no-color` | 强制开启 / 关闭彩色输出（默认：非 Windows 终端自动开启）。也可设环境变量 `QDIR_COLOR=1`。 |

> 忘了参数时可以随时 `--help`（简版，含 6 条示例）或 `--guide`（完整版）。
> 本文内容就是 `--guide` 的展开版。

---

## 5. 典型场景

### 场景 1：先看看能不能打（推荐第一步）

```bash
python qdir_colorfilter_unlimit.py --check
```

输出（节选）：

```text
[>] 步骤 3: 检查当前补丁状态
  [i] 上限点 5 处，当前一致值: 0x20 (32)
  [i] 数组引用 17/17 | 扩容节 .qdcol: 无
  [OK] 结论: 原版（上限 32），可以打补丁
```

三种结论：

| 结论 | 含义 | 该怎么做 |
| --- | --- | --- |
| 原版（上限 32），可以打补丁 | 正常 | 直接执行打补丁命令 |
| 已打补丁（上限 N） | 已经改过了 | 不用再打；要重打先 `--restore` |
| 不适用（五处上限值不一致） | **不是 Q-Dir 12.77 x64** | 换对版本的 exe，或 `--pick` 换候选 |

### 场景 2：默认打补丁（最安全）

```bash
python qdir_colorfilter_unlimit.py
```

- 自动找 exe → 备份成 `Q-Dir.exe.orig` → 输出 `Q-Dir_patched.exe`；
- **原文件完全不动**，出问题删掉 `_patched` 即可。

关键输出：

```text
  [OK] 输出文件: D:\...\Q-Dir_Portable_x64\Q-Dir\Q-Dir_patched.exe (1.86 MB)
  [i] 数组 RVA 0x1f3000 | 上限 32 -> 127 | 搬迁引用 17 | 新区段容量 4096
[OK] 复检通过：五处上限点 + 渲染守卫 + 初始化清理全部符合 127
[OK] 完成：请把 Q-Dir_patched.exe 复制覆盖到 Q-Dir 安装目录后运行验证
```

### 场景 3：直接替换原文件

```bash
python qdir_colorfilter_unlimit.py --in-place
```

会先备份成 `Q-Dir.exe.orig` 再覆盖。之后直接双击 Q-Dir 就能用。

### 场景 4：只扩到 64 条

```bash
python qdir_colorfilter_unlimit.py --max 64
```

`--max` 必须在 32~127 之间，否则：

```text
[x] --max 必须在 32~127（cmp r32,imm8 有符号立即数上限 127）
```

### 场景 5：指定输出位置

```bash
python qdir_colorfilter_unlimit.py --max 64 --out "D:/Temp/Q-Dir_64.exe"
```

### 场景 6：看看都找到了哪些 exe

```bash
python qdir_colorfilter_unlimit.py --list
```

输出示例：

```text
  [i] 搜索根目录 (4):
        - D:\Software\ToolsSoftware\Q-Dir\Q-Dir
        - D:\Software\ToolsSoftware\Q-Dir
        - D:\Software\ToolsSoftware\Q-Dir\Q-Dir_Portable_x64
        - D:\Software\ToolsSoftware\Q-Dir\Q-Dir_Portable_x64\Q-Dir
      匹配模式: Q-Dir*.exe, QDir*.exe | 目录深度: 3 | 最小体积: 200.00 KB
      已跳过 3 个备份/系统目录（--include-backup 可关闭）
  [i] 共找到 1 个候选文件：
    [*] [1] D:\Software\ToolsSoftware\Q-Dir\Q-Dir_Portable_x64\Q-Dir\Q-Dir.exe
           1.86 MB | x64 | 修改时间 2026-09-08 13:22 | 得分 130  <= 已选中
  [OK] 自动选择: D:\Software\ToolsSoftware\Q-Dir\Q-Dir_Portable_x64\Q-Dir\Q-Dir.exe
```

### 场景 7：自动选错了，换一个候选

```bash
python qdir_colorfilter_unlimit.py --list          # 先看编号
python qdir_colorfilter_unlimit.py --pick 3        # 用第 3 个
```

或干脆给完整路径，跳过搜索：

```bash
python qdir_colorfilter_unlimit.py --exe "D:/Game/Q-Dir/Q-Dir-x64.exe"
```

### 场景 8：Q-Dir 装在别的地方

```bash
python qdir_colorfilter_unlimit.py --search-dir "D:/Tools" --depth 5
python qdir_colorfilter_unlimit.py --dir "D:/Tools/Q-Dir"     # 只搜这一个目录
```

### 场景 9：还原

```bash
python qdir_colorfilter_unlimit.py --restore
```

```text
[OK] 已还原: D:\...\Q-Dir.exe  <-  D:\...\Q-Dir.exe.orig
```

### 场景 10：批量 / 自动化调用

```bash
python qdir_colorfilter_unlimit.py --check --quiet; echo "exit=$?"
```

`--quiet` 只保留结果与错误，配合退出码写脚本（见第 7 节）。

---

## 6. 输出信息怎么读

脚本按步骤输出，每一步之间有一条分隔线：

| 步骤 | 标题 | 说明 |
| --- | --- | --- |
| 1 | 定位 Q-Dir 可执行文件 | 打印搜索根目录、匹配模式、候选列表、最终选中的文件 |
| 2 | 载入并校验 PE | 校验是不是 PE64（AMD64），打印 ImageBase 与 .text 信息 |
| 3 | 检查当前补丁状态 | 打印 5 处上限值、数组引用数 17/17、`.qdcol` 是否已存在 |
| 4 | 备份原文件 | 生成或复用 `<exe>.orig` |
| 5 | 应用补丁 | 打印目标上限、是否搬迁数组 |
| 6 | 写出结果 | 输出文件路径、新数组 RVA、搬迁引用数、新区段容量 |
| 7 | 复检输出文件 | 重新解析输出文件，逐项比对，通过才打印 `[OK] 复检通过` |

图标含义：

```text
[i]  信息        [OK] 成功/通过        [!] 警告
[x]  错误        [>] 步骤标题          [*] 当前选中的候选
```

---

## 7. 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功；`--check` 时表示「原版可打补丁」或「已打补丁无需重复」 |
| `1` | 载入失败 / 预检失败（已打补丁或版本不符）/ 打补丁失败 / 复检失败 / `--restore` 找不到备份 |
| `2` | 参数非法（`--max` 越界、`--only` 越界、`--pick` 越界）或**没找到任何候选 exe** |
| `130` | 用户按 Ctrl+C 中断 |

---

## 8. 打完补丁后怎么部署

1. **退出 Q-Dir**（右下角托盘图标也要退）。
2. 默认模式会生成 `Q-Dir_patched.exe`，把它**改名/复制覆盖**成安装目录下的 `Q-Dir.exe`：

   ```bash
   copy /Y "Q-Dir_patched.exe" "D:\Software\ToolsSoftware\Q-Dir\Q-Dir_Portable_x64\Q-Dir\Q-Dir.exe"
   ```

   建议先手动把原 `Q-Dir.exe` 复制一份（脚本已经生成过 `.orig`，保险起见可再存一份）。
3. 启动 Q-Dir → 菜单/设置里打开 **Color Filter（颜色过滤器）**，添加超过 32 条规则，保存、重启 Q-Dir，确认规则条数仍在、颜色照常生效。
4. 出问题就把 `Q-Dir.exe.orig` 复制回来，或执行 `--restore`。

---

## 9. 备份与回滚

| 文件 | 作用 |
| --- | --- |
| `Q-Dir.exe.orig` | 脚本在首次打补丁时自动创建的**原版备份**，不会被二次覆盖 |
| `Q-Dir_patched.exe` | 默认模式的产物，原文件保持不变 |

回滚方式（任选）：

```bash
python qdir_colorfilter_unlimit.py --restore              # 脚本还原
copy /Y "Q-Dir.exe.orig" "Q-Dir.exe"                      # 手工覆盖
```

> 注意：`.orig` 与 `--restore` 都跟**同一个 exe 路径**绑定。换过 `--exe`/`--pick` 后，请确认还原的是你要的那个文件。

---

## 10. 常见问题（FAQ）

**Q1：提示「没有找到任何匹配的 Q-Dir 可执行文件」**
按顺序试：`--search-dir <你的 Q-Dir 目录>` → `--depth 5` → `--include-backup` → `--exe <完整路径>`。脚本会打印 4 条对应建议。

**Q2：提示「预检失败: 当前上限已是 127」**
说明这个文件已经打过补丁了。重复打会因特征不匹配报错。要重新打就先 `--restore`，确认无误再加 `--force`。

**Q3：提示「只支持 AMD64 Q-Dir」/ 候选显示 `x86`**
你选中的是 32 位 Q-Dir。本补丁只支持 64 位；换 64 位版本的 exe，或用 `--pick` 选列表里 `x64` 的那一个（脚本会优先选 x64，并给出警告）。

**Q4：提示「打补丁失败: 数组引用不完整: 缺 [...]」**
通常是：① 文件已打过补丁；② 版本不是 12.77 x64。脚本**不会**生成半成品文件，原文件保持不变。

**Q5：提示「写入失败: 文件被占用或只读」**
Q-Dir 还在运行，或目标目录只读/受保护。完全退出 Q-Dir；便携版放桌面/用户目录，不要直接放 `Program Files`。

**Q6：`--max` 能不能超过 127？**
不能。代码里是 `cmp r32, imm8` 有符号立即数，最大 127；再大需要改指令编码，超出本脚本范围。

**Q7：为什么默认不直接覆盖原文件？**
为了可回滚。默认输出到 `<name>_patched.exe`，你确认能用后再手工覆盖；想一步到位用 `--in-place`。

**Q8：控制台中文乱码怎么办？**
脚本已强制 UTF-8 输出。若仍乱码，在命令前执行 `chcp 65001`，或加 `--no-color`。

**Q9：`--force` / `--only` / `--no-reloc` 是什么？
它们是调试开关，正式补补丁不要用：
- `--force`：跳过预检，可能在错误的文件上写入；
- `--only 0,1`：只改 5 个上限点中的某几个，产物不完整；
- `--no-reloc`：不搬迁数组，容量仍被原位置限制，扩大上限会越界。

**Q10：想看有哪些命令行参数？**

```bash
python qdir_colorfilter_unlimit.py --help
```

---

## 11. 安全须知

- 只对自己电脑上合法持有的 Q-Dir 使用，补丁产物请勿分发。
- 打补丁前退出 Q-Dir，别在 Q-Dir 运行时覆盖它的 exe。
- 不要对已打补丁的文件重复执行；`--check` 可以帮你确认状态。
- 换 Q-Dir 版本后，需要重新对**新版本的原版 exe** 打补丁，旧的 `.orig`/`_patched` 都不能混用。
