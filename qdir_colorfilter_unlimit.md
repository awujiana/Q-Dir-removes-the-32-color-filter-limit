# `qdir_colorfilter_unlimit.py` 文档

## 1. 文件功能概述

`qdir_colorfilter_unlimit.py` 是一个面向 **Q-Dir 12.77 x64** 的 PE 二进制补丁生成器，用于解除颜色筛选器（Color Filter）最多 32 条的限制。

脚本的主要工作包括：

1. 读取并校验目标 Q-Dir 可执行文件；
2. 确认目标为 AMD64 PE 文件，并定位 `.text` 节；
3. 检查颜色筛选器数组及其 RIP 相对引用；
4. 在 PE 文件中追加 `.qdcol` 节，把颜色筛选器数组迁移到新节；
5. 修正发现的 17 处数组引用；
6. 将载入、保存、解析路径中的上限值从 `32` 修改为用户指定值，默认是 `127`；
7. 修改颜色渲染阶段的样式索引守卫；
8. 修改启动时的颜色对象清理上限；
9. 写出新的补丁版 EXE，并执行静态复检；
10. 支持检查当前文件状态、输出副本以及根据 `.orig` 备份还原。

脚本只针对预先分析过的 Q-Dir 版本和固定地址特征工作。它不是通用 PE 修改器，也不应直接用于其他版本的 Q-Dir。

> 注意：当前脚本只处理颜色筛选器扩容。与 `0x5247F4` 崩溃相关的分析和候选修复不属于本文件。

---

## 2. 运行环境与依赖

### 2.1 Python 版本

脚本使用 Python 3 语法，建议使用 Python 3.8 或更高版本。

### 2.2 第三方依赖

脚本启动时导入：

```python
import pefile
import capstone
```

如果依赖缺失，脚本会终止并提示：

```text
需要 pefile
```

或：

```text
需要 capstone
```

依赖用途如下：

| 依赖 | 用途 |
| --- | --- |
| `pefile` | 读取 PE 头、节表、Optional Header 和导入/文件结构信息 |
| `capstone` | 反汇编 `.text` 节，用于识别 RIP 相对寻址引用 |

---

## 3. 模块与核心结构

文件没有拆分为多个 Python 模块，所有功能集中在一个脚本中，结构可以分为以下几层：

```text
命令行入口 main()
    |
    +-- 参数解析与目标路径探测
    |
    +-- Target
    |       +-- PE 文件读取
    |       +-- VA 到文件偏移转换
    |       +-- 上限点校验
    |       +-- 颜色数组引用扫描
    |
    +-- apply_patch()
    |       +-- add_section()
    |       +-- 颜色数组迁移
    |       +-- RIP 相对位移修正
    |       +-- 五处上限修改
    |       +-- 渲染守卫修改
    |       +-- 启动清理上限修改
    |
    +-- 输出补丁文件
    +-- Target.verify() 静态复检
    +-- 备份还原
```

### 3.1 地址模型

脚本中的主要地址是 **RVA** 或基于 ImageBase 的 **VA**。目标程序默认使用：

```text
ImageBase = 0x400000
```

`Target.va2off()` 使用下面的关系将虚拟地址转换为文件偏移：

```text
FileOffset = VA - ImageBase - .text.VirtualAddress + .text.PointerToRawData
```

该计算只适用于脚本当前使用的 `.text` 地址场景；新增节的写入使用节表中的 `PointerToRawData`。

---

## 4. 全局常量与数据结构

### 4.1 文件与数组布局常量

```python
EXE_NAME = "Q-Dir.exe"
ARRAY_RVA, ARRAY_STRIDE, COUNT_RVA, OLD_MAX = 0x1544F0, 0x20, 0x15447C, 0x20
```

| 常量 | 含义 |
| --- | --- |
| `EXE_NAME` | 默认目标文件名 |
| `ARRAY_RVA` | 原颜色筛选器数组的起始 RVA |
| `ARRAY_STRIDE` | 单个颜色筛选器对象的大小，`0x20` 字节 |
| `COUNT_RVA` | 颜色筛选器计数位置的 RVA；当前代码中作为布局说明常量保留 |
| `OLD_MAX` | 原始颜色筛选器上限，数值为 `0x20`，即 32 |

原数组容量为：

```text
32 * 0x20 = 0x400 字节
```

### 4.2 `LOOP_SITES`

`LOOP_SITES` 保存五个需要修改上限的代码位置及其原始字节特征：

```python
LOOP_SITES = [
    (0x4B3390, bytes([0x83, 0xFB, 0x20])),
    (0x4B37B8, bytes([0x83, 0xFF, 0x20])),
    (0x4AA286, bytes([0x83, 0x3B, 0x20])),
    (0x4AA6D4, bytes([0xB8, 0x20, 0, 0, 0])),
    (0x4AAABE, bytes([0xB8, 0x20, 0, 0, 0])),
]
```

前三处是带 `0x20` 立即数的比较指令，后两处是把 `0x20` 装入寄存器的指令。补丁时只替换立即数部分，保留其他操作码和 ModR/M 字节。

### 4.3 其他修改点

```python
RENDER_GUARD = (0x4B3A6C, bytes.fromhex("83 7e 18 1f"))
INIT_CLEAR = (0x522C8B, bytes.fromhex("b9 1f 00 00 00"))
```

- `RENDER_GUARD`：颜色应用阶段的样式索引守卫，原始最大索引为 `31`；
- `INIT_CLEAR`：启动时清理颜色对象的循环上限，原始值为 `31`，修改后使用 `new_max - 1`。

### 4.4 `EXPECTED_REF_VAS`

该集合列出预期发现的 17 个颜色数组引用位置：

```python
EXPECTED_REF_VAS = {
    0x4A67DA, 0x4AA801, 0x4AAB98, 0x4B2B15, 0x4B30AA, 0x4B3348,
    0x4B34AA, 0x4B3AAC, 0x4B4BC1, 0x4B4CDC, 0x4AD1F3, 0x4B3061,
    0x4B307F, 0x4B2F95, 0x4AA791, 0x4B34B4, 0x522C90,
}
```

扫描结果必须与该集合完全一致。缺少引用时，脚本会拒绝继续打补丁，以避免产生部分修复的文件。

### 4.5 `NEW_SECTION_NAME`

```python
NEW_SECTION_NAME = b".qdcol"
```

新增 PE 节名称为 `.qdcol`。该节用于存放扩容后的颜色筛选器数组，节属性为：

```text
0xC0000040 = 可读 + 可写的数据节属性
```

---

## 5. 主要函数与参数说明

## 5.1 `align_up(v, a)`

```python
def align_up(v, a): return (v + a - 1) // a * a
```

### 用途

将 `v` 向上对齐到 `a` 的整数倍。PE 节的 RVA 和文件偏移通常需要满足节对齐或文件对齐要求。

### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `v` | `int` | 待对齐的数值 |
| `a` | `int` | 对齐粒度 |

### 返回值

返回不小于 `v` 的最小 `a` 的整数倍。

示例：

```python
align_up(4064, 0x1000)  # 4096
```

---

## 5.2 `class Target`

`Target` 封装目标 PE 文件及反汇编环境，是脚本的核心数据结构。

### `Target.__init__(path)`

```python
def __init__(self, path):
```

#### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `path` | `str` | 目标 Q-Dir 可执行文件路径 |

#### 主要行为

1. 读取文件为 `bytearray`；
2. 使用 `pefile.PE` 解析 PE；
3. 检查 `Machine` 是否为 AMD64；
4. 读取 ImageBase；
5. 定位 `.text` 节；
6. 初始化 Capstone x86-64 反汇编器；
7. 开启 `detail` 和 `skipdata` 模式。

其中 `skipdata = True` 用于让反汇编器在遇到数据字节或无法识别的字节时继续扫描，而不是立即中止。

### `Target.va2off(va)`

```python
def va2off(self, va):
```

#### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `va` | `int` | 目标虚拟地址 |

#### 返回值

返回该虚拟地址在文件中的偏移。

如果地址不在文件数据范围内，会抛出：

```python
RuntimeError("VA 不在文件中: %#x" % va)
```

### `Target.verify(want_max=OLD_MAX)`

```python
def verify(self, want_max=OLD_MAX):
```

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `want_max` | `int` | `OLD_MAX` | 期望五个上限点使用的值 |

#### 返回值

返回问题列表：

```python
[]
```

表示所有上限点均符合预期；非空列表表示至少一个位置的字节不匹配。

#### 关键逻辑

- 遍历 `LOOP_SITES`；
- 根据指令长度构造期望字节；
- 使用 `va2off()` 读取实际字节；
- 将实际值与期望值逐项比较。

### `Target.scan_array_refs()`

```python
def scan_array_refs(self):
```

#### 参数

无显式参数，使用对象内部的 PE 数据和全局地址常量。

#### 返回值

返回字典：

```python
{
    source_va: (displacement_file_offset, target_rva),
}
```

其中：

- `source_va`：预期的引用指令地址；
- `displacement_file_offset`：RIP 相对位移字段在文件中的偏移；
- `target_rva`：引用最终指向的 RVA。

#### 关键逻辑

1. 读取 `.text` 原始数据；
2. 将每个连续四字节解释为有符号 RIP displacement；
3. 遍历可能的指令长度 `4..8`；
4. 判断计算出的目标是否落在原数组第一个槽位范围内；
5. 在位移字段前最多 10 字节内尝试匹配预期指令地址；
6. 使用 Capstone 重新反汇编并确认该指令确实包含 RIP 相对寻址；
7. 记录有效引用。

该函数不会把 `RVA 0x1548F0` 的对象管理哨兵误当成颜色数组引用，因为扫描范围只针对：

```python
ARRAY_RVA <= target < ARRAY_RVA + ARRAY_STRIDE
```

---

## 5.3 `add_section(tgt, name, vsize, raw)`

```python
def add_section(tgt, name, vsize, raw):
```

### 用途

向目标 PE 文件追加一个新节，并更新：

- 节表中的新节头；
- PE 文件的节数量；
- `SizeOfImage`；
- 文件末尾的对齐数据。

### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `tgt` | `Target` | 目标 PE 封装对象 |
| `name` | `bytes` | 节名称，例如 `b".qdcol"` |
| `vsize` | `int` | 节的虚拟大小 |
| `raw` | `bytes` | 要写入该节的原始数据 |

### 返回值

返回新节的 RVA：

```python
return rva
```

### 关键逻辑

1. 计算新节头位置；
2. 检查 PE 头部是否存在可用的节表空间；
3. 计算新节 RVA；
4. 将文件长度对齐到 `FileAlignment`；
5. 追加原始节数据；
6. 写入节头；
7. 更新节数；
8. 更新 `SizeOfImage`。

如果节表没有空间，会抛出：

```python
RuntimeError("PE 头部没有可用节表空间")
```

---

## 5.4 `apply_patch(tgt, new_max, only=None, relocate=True)`

```python
def apply_patch(tgt, new_max, only=None, relocate=True):
```

### 用途

执行实际的颜色筛选器扩容补丁。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `tgt` | `Target` | 无 | 已加载的目标 PE 文件 |
| `new_max` | `int` | 无 | 新的颜色筛选器上限，命令行限制为 `32..127` |
| `only` | `list[int] \\| None` | `None` | 只修改 `LOOP_SITES` 中指定下标的位置；为 `None` 时修改全部位置 |
| `relocate` | `bool` | `True` | 是否迁移颜色筛选器数组到 `.qdcol` 新节 |

### 返回值

返回三元组：

```python
(new_rva, cap, ref_count)
```

| 返回值 | 说明 |
| --- | --- |
| `new_rva` | 新数组所在节的 RVA；不迁移时为原数组 RVA |
| `cap` | 新节容量；不迁移时为 `0` |
| `ref_count` | 修正的数组引用数量 |

### 关键逻辑

#### 1. 迁移数组

当 `relocate=True` 时：

```python
cap = align_up(new_max * ARRAY_STRIDE, 0x1000)
```

例如上限为 127 时：

```text
127 * 0x20 = 4064 字节
对齐后容量 = 0x1000 = 4096 字节
```

随后追加 `.qdcol` 节，并计算：

```python
delta = new_rva - ARRAY_RVA
```

#### 2. 校验 17 处引用

```python
refs = tgt.scan_array_refs()
if set(refs) != EXPECTED_REF_VAS:
    raise RuntimeError(...)
```

如果发现的引用集合与预期不同，脚本立即终止，避免只修正部分引用。

#### 3. 修正 RIP displacement

RIP 相对寻址的位移需要加上数组搬迁距离：

```python
old = struct.unpack_from("<i", tgt.data, disp_off)[0]
struct.pack_into("<i", tgt.data, disp_off, old + delta)
```

#### 4. 修改五处上限

对于三字节比较指令：

```python
old[:2] + bytes([new_max])
```

对于五字节立即数指令：

```python
old[:1] + bytes([new_max, 0, 0, 0])
```

#### 5. 修改渲染守卫

原始指令特征：

```text
83 7E 18 1F
```

修改为：

```text
83 7E 18 <new_max>
```

#### 6. 修改启动清理上限

原始值是 `31`，表示清理索引 `31..0`。新值使用：

```python
new_max - 1
```

例如：

```text
new_max = 127
清理上限 = 126
```

这样可以覆盖索引 `126..0`。

### `only` 参数行为

如果传入 `only`，脚本只修改指定的 `LOOP_SITES` 条目，但渲染守卫和初始化清理只在 `only is None` 时修改。

示例：

```python
apply_patch(target, 64, only=[0, 1])
```

表示只修改 `LOOP_SITES[0]` 和 `LOOP_SITES[1]`。

### `relocate=False` 行为

当 `relocate=False` 时：

- 不追加 `.qdcol`；
- 不迁移数组；
- 不修正数组 RIP 引用；
- 仍会修改上限点。

该模式适合调试单独的上限修改，但不适合真正扩大数组容量，因为原数组后方存在对象管理哨兵，继续在原位置扩容可能覆盖其他结构。

---

## 5.5 `current_max(t)`

```python
def current_max(t):
```

### 用途

读取五个上限点的立即数，判断它们是否一致。

### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `t` | `Target` | 已加载的目标 PE 文件 |

### 返回值

- 五处值一致：返回该值；
- 五处值不一致：返回 `None`。

该函数用于 `--check` 模式判断当前文件是原版、已打补丁，还是不适用于当前版本。

---

## 5.6 `has_patch_section(t, name=NEW_SECTION_NAME)`

```python
def has_patch_section(t, name=NEW_SECTION_NAME):
```

### 用途

检查 PE 节表中是否存在指定名称的节。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `t` | `Target` | 无 | 目标 PE 对象 |
| `name` | `bytes` | `b".qdcol"` | 要检查的节名称 |

### 返回值

返回布尔值：

```python
True   # 存在
False  # 不存在
```

---

## 5.7 `main()`

```python
def main():
```

### 用途

命令行入口，负责参数解析、路径探测、备份、打补丁、输出和复检。

### 命令行参数

> 脚本内置了完整使用指引，命令行执行 `--guide` 即可打印（面向使用者，内容为
> `Q-Dir颜色过滤器扩容_使用指南.md` 的精简版）；`--help` 为简版（含 6 条示例）。

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--exe` | 文件名/路径 | `Q-Dir.exe` | 目标文件名（支持 `*`、`?`）或完整路径；给完整路径时不做搜索 |
| `--dir` | 路径 | 自动探测 | 把搜索范围限定在该目录内 |
| `--search-dir` | 路径 | 无 | 追加一个搜索根目录，可重复指定 |
| `--depth` | 整数 | `3` | 搜索目录深度 |
| `--pick` | 整数 | 第 1 个 | 使用候选列表中的第 N 个文件 |
| `--include-backup` | 开关 | 关闭 | 搜索时不跳过备份/系统目录 |
| `--list` | 开关 | 关闭 | 只列出候选 exe 并退出 |
| `--max` | 整数 | `127` | 新上限，必须在 `32..127` |
| `--out` | 路径 | 自动生成 | 指定输出文件路径 |
| `--in-place` | 开关 | 关闭 | 就地覆盖输入文件 |
| `--check` | 开关 | 关闭 | 只检查，不打补丁 |
| `--restore` | 开关 | 关闭 | 从 `<exe>.orig` 还原 |
| `--only` | 逗号分隔索引 | 无 | 只修改指定的上限点，取值 `0..4` |
| `--no-reloc` | 开关 | 关闭 | 不迁移数组，仅修改代码常量 |
| `--force` | 开关 | 关闭 | 跳过「已打补丁/版本不匹配」的预检拦截 |
| `--quiet` | 开关 | 关闭 | 只输出关键结果与错误 |
| `--guide` | 开关 | 关闭 | 打印内置完整使用指引后退出（`print_guide()`） |
| `--color` / `--no-color` | 开关 | 自动 | 强制开启 / 关闭彩色输出 |

### 默认目录探测（自动搜索）

未传入 `--dir`、且 `--exe` 不是完整路径时，脚本按以下顺序构造搜索根目录（去重后逐个遍历，深度由 `--depth` 控制）：

1. 脚本所在目录；
2. 当前工作目录；
3. 脚本目录的父目录；
4. 脚本目录与父目录下的常见安装子目录：`Q-Dir`、`Q-Dir_Portable_x64`、`Q-Dir_Portable`、`Q-Dir_x64`、`Q-Dir_x84`、`x64`、`x84`、`bin`、`Portable`；
5. 父目录下名字包含 `q-dir` 或 `qdir` 的子目录，以及它们的 `Q-Dir` 子目录。

匹配规则与排序：

- 文件名不区分大小写匹配 `Q-Dir*.exe` / `QDir*.exe`，覆盖 `Q-Dir.exe`、`Q-Dir-x64.exe`、`Q-Dir-x84.exe` 等命名；小于 `MIN_EXE_SIZE`（200 KB）的 exe 忽略。
- 默认跳过名字含 `备份` / `待删除` / `backup` / `_bak` / `.git` / `node_modules` 等关键字的目录，`--include-backup` 可关闭。
- 候选按得分排序：`Q-Dir.exe` = 100，`Q-Dir-x64.exe` = 92，`Q-Dir-x84.exe` = 90，其余 `Q-Dir*.exe` = 50；命中 `patched`/`bak`/`备份` 等词 −45；x64 +30、x86 −25；每深一层 −3；同分按修改时间新的优先。
- 得分最高者自动选中；`--pick N` 可手工指定，找不到任何候选时退出码为 `2` 并打印排查建议。

### 备份行为

如果 `<exe>.orig` 不存在，脚本会先创建：

```python
shutil.copy2(exe, orig)
```

之后默认不覆盖输入文件，而是输出到：

```text
Q-Dir_patched.exe
```

只有使用 `--in-place` 时才会直接覆盖输入文件。

### `--check` 模式

执行检查时，脚本会输出：

- 文件路径；
- 五处上限是否一致；
- 颜色数组引用数量；
- `.qdcol` 是否存在；
- 当前文件是原版、已打补丁还是不适用。

### `--restore` 模式

如果存在 `<exe>.orig`，执行：

```text
python qdir_colorfilter_unlimit.py --restore
```

脚本会用备份文件覆盖当前 EXE。

### 5.8 `GUIDE_TEXT` / `print_guide()`

模块级常量 `GUIDE_TEXT` 保存面向使用者的完整指引文本（快速开始、自动搜索规则、
常用参数、典型场景、输出与退出码、备份回滚、FAQ、注意事项），`print_guide()`
逐行打印它。

`main()` 在解析参数后最先处理 `--guide`：打印指引并直接返回 `0`，不做搜索、
不校验 `--max`、不碰任何文件，因此可离线、安全地随时查看。

找不到候选 EXE 时的排查建议里也会提示 `--guide`。

---

## 6. 关键逻辑说明

### 6.1 为什么必须迁移数组

原颜色筛选器数组位于：

```text
RVA 0x1544F0
```

每个对象占：

```text
0x20 字节
```

原数组后方的：

```text
RVA 0x1548F0
```

是对象管理哨兵区域，不是颜色筛选器数组的第 33 个槽位。因此不能简单地把原数组后方继续扩展，否则可能覆盖对象管理结构。

脚本选择：

1. 新增 `.qdcol` 节；
2. 将数组容量放入新节；
3. 修正颜色数组的 17 处 RIP 相对引用；
4. 保留旧地址后方的对象管理哨兵。

### 6.2 为什么上限最大为 127

脚本将部分 `cmp r32, imm8` 指令中的立即数改为新上限。x86-64 指令编码中的有符号八位立即数可安全使用到 `127`，所以命令行限制为：

```text
32 <= --max <= 127
```

超过 127 时脚本拒绝执行：

```text
--max 必须在 32~127（cmp r32,imm8 有符号立即数上限 127）
```

### 6.3 为什么必须做特征校验

地址是针对特定 Q-Dir 版本分析得到的。如果输入文件版本不同，同一地址可能对应完全不同的指令。脚本通过以下方式降低误修改风险：

- 检查 AMD64 架构；
- 检查原始指令字节；
- 检查 `.text` 节；
- 检查 17 处数组引用；
- 修改后重新读取并复检。

### 6.4 输出文件与输入文件的关系

默认行为：

```text
输入：Q-Dir.exe
输出：Q-Dir_patched.exe
备份：Q-Dir.exe.orig
```

这样可以在不破坏原文件的前提下进行运行时验证。只有确认补丁版稳定后，才应考虑使用 `--in-place`。

---

## 7. 使用示例

> 面向使用者的完整说明见同目录下的 `Q-Dir颜色过滤器扩容_使用指南.md`。
> 本节只给命令行示例。除 7.6 外，均可省略 `--exe`：脚本会自动搜索
> `Q-Dir.exe` / `Q-Dir-x64.exe` / `Q-Dir-x84.exe` 等命名并挑选得分最高的候选。

### 7.0 查看自动搜索结果（不修改任何文件）

```bash
python qdir_colorfilter_unlimit.py --list
```

```text
  [i] 共找到 1 个候选文件：
    [*] [1] D:\Software\ToolsSoftware\Q-Dir\Q-Dir_Portable_x64\Q-Dir\Q-Dir.exe
           1.86 MB | x64 | 修改时间 2026-09-08 13:22 | 得分 130  <= 已选中
  [OK] 自动选择: D:\Software\ToolsSoftware\Q-Dir\Q-Dir_Portable_x64\Q-Dir\Q-Dir.exe
```

### 7.1 检查原版是否适用

```bash
python qdir_colorfilter_unlimit.py --check
```

预期结论类似：

```text
  [i] 上限点 5 处，当前一致值: 0x20 (32)
  [i] 数组引用 17/17 | 扩容节 .qdcol: 无
  [OK] 结论: 原版（上限 32），可以打补丁
```

也可显式指定目录与文件名：

```bash
python qdir_colorfilter_unlimit.py \
  --dir "D:/Software/ToolsSoftware/Q-Dir/Q-Dir" \
  --exe Q-Dir_org.exe \
  --check
```

### 7.2 生成上限 127 的补丁版

```bash
python qdir_colorfilter_unlimit.py
```

默认输出：

```text
Q-Dir_patched.exe
```

### 7.3 指定输出路径

```bash
python qdir_colorfilter_unlimit.py \
  --exe Q-Dir.exe \
  --max 64 \
  --out "D:/Temp/Q-Dir_64.exe"
```

### 7.4 就地覆盖

```bash
python qdir_colorfilter_unlimit.py --in-place
```

会先生成 `<exe>.orig` 备份，再覆盖目标文件。

### 7.5 指定候选 / 追加搜索目录

```bash
python qdir_colorfilter_unlimit.py --pick 2                      # 用第 2 个候选
python qdir_colorfilter_unlimit.py --search-dir "D:/Tools" --depth 5
python qdir_colorfilter_unlimit.py --exe "D:/Tools/Q-Dir/Q-Dir-x64.exe"
```

### 7.6 还原输入程序

```bash
python qdir_colorfilter_unlimit.py --restore
```

### 7.7 只修改部分上限点（调试用途）

```bash
python qdir_colorfilter_unlimit.py \
  --exe Q-Dir_org.exe \
  --max 64 \
  --only 0,1
```

此模式只修改 `LOOP_SITES[0]` 和 `LOOP_SITES[1]`，不建议作为最终补丁使用。

---

## 8. 错误处理与边界条件

### 8.1 `--max` 越界

```text
--max 必须在 32~127
```

处理方式：退出，不修改文件。

### 8.2 目标不是 AMD64

```text
只支持 AMD64 Q-Dir
```

处理方式：构造 `Target` 时抛出异常并终止。

### 8.3 PE 头部没有节表空间

```text
PE 头部没有可用节表空间
```

处理方式：不追加新节，补丁失败。

### 8.4 数组引用不完整

```text
数组引用不完整: 缺 [...]
```

处理方式：不继续修正引用，防止生成部分迁移的文件。

### 8.5 指令特征不匹配

例如渲染守卫或初始化清理位置的原始字节发生变化时，脚本会终止。这通常表示：

- 目标不是预期的 Q-Dir 版本；
- 文件已经被其他补丁修改；
- 地址或特征需要重新分析。

### 8.6 原版后方对象管理哨兵

脚本不能把 `RVA 0x1548F0` 当作颜色数组的一部分。任何把原数组直接扩展到该位置的改法，都需要重新确认对象管理结构布局。

### 8.7 找不到任何候选 EXE

```text
[x] 没有找到任何匹配的 Q-Dir 可执行文件
  [!] 可以试试（任选其一）：
    [!] 1) --search-dir <目录>  追加一个搜索根目录（可重复指定）
    [!] 2) --depth 5            加大搜索深度（当前 3）
    [!] 3) --include-backup     连备份目录一起搜索
    [!] 4) --exe <完整路径>     直接给出 exe 路径
```

退出码 `2`，不修改任何文件。

### 8.8 预检拦截（已打补丁 / 版本不符）

```text
[x] 预检失败: 当前上限已是 127（原版应为 32），文件可能已打过补丁
```

打补丁前若 `current_max()` 不等于 `OLD_MAX`，脚本默认终止（退出码 `1`），
避免二次打补丁把文件写坏；`--force` 可强制执行，`--restore` 可先还原。
`--check` 与 `--only` 模式不受此拦截影响。

---

## 9. 验证建议

补丁生成后至少进行以下验证：

### 静态验证

```bash
python qdir_colorfilter_unlimit.py \
  --dir "目标目录" \
  --exe Q-Dir_patched.exe \
  --check
```

应确认：

- 五处上限值一致；
- 上限为期望值；
- `.qdcol` 存在；
- 数组引用已迁移；
- 输出文件可以被 PE 工具正常读取。

### 运行时验证

建议分别测试：

```text
32 条
33 条
40 条
64 条
127 条
```

重点观察：

- 第 33 条是否实际载入；
- `m_Farben_count` 是否达到目标值；
- 第 33、40、64、127 个槽位是否有有效数据；
- 重启后配置是否保持；
- 保存规则时是否被截断；
- 关闭和重新打开 Q-Dir 是否稳定；
- 颜色渲染是否正常。

### 原版对照

应使用未修改的 `Q-Dir_org.exe` 做对照，确保测试差异来自补丁，而不是 Q-Dir 自身已有问题。

---

## 10. 完整源代码（保留原有代码注释）

下面保留当前 `qdir_colorfilter_unlimit.py` 的完整源代码，包括原有中文注释、特征字节和命令行逻辑。

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q-Dir Color Filter 32 条上限补丁

针对 Q-Dir 12.77 x64：
* [Filter2] 规则对象数组位于 RVA 0x1544F0，单项 0x20 字节；
* 规则计数位于 RVA 0x15447C；
* 载入/保存/解析路径的五个 0x20 常量改为新的上限；
* 原数组后方 RVA 0x1548F0 是 Q-Dir 的对象管理哨兵，不是颜色数组的一部分，
  因此迁移颜色数组时不能把它覆盖掉。

补丁默认生成可回滚的副本，并校验 PE 特征。
"""
import argparse, os, shutil, struct, sys
try:
    import pefile
except ImportError:
    sys.exit("需要 pefile")
try:
    import capstone
except ImportError:
    sys.exit("需要 capstone")

EXE_NAME = "Q-Dir.exe"
ARRAY_RVA, ARRAY_STRIDE, COUNT_RVA, OLD_MAX = 0x1544F0, 0x20, 0x15447C, 0x20
LOOP_SITES = [
    (0x4B3390, bytes([0x83, 0xFB, 0x20])),
    (0x4B37B8, bytes([0x83, 0xFF, 0x20])),
    (0x4AA286, bytes([0x83, 0x3B, 0x20])),
    (0x4AA6D4, bytes([0xB8, 0x20, 0, 0, 0])),
    (0x4AAABE, bytes([0xB8, 0x20, 0, 0, 0])),
]
# 颜色应用阶段还会把规则中的样式索引限制在 0..31。
RENDER_GUARD = (0x4B3A6C, bytes.fromhex("83 7e 18 1f"))
# 启动时清空 32 个颜色对象；循环从 imm 倒数到 0。
INIT_CLEAR = (0x522C8B, bytes.fromhex("b9 1f 00 00 00"))
# 仅迁移颜色规则数组的引用；不得迁移 0x1548F0 处的对象管理结构。
EXPECTED_REF_VAS = {
    0x4A67DA, 0x4AA801, 0x4AAB98, 0x4B2B15, 0x4B30AA, 0x4B3348,
    0x4B34AA, 0x4B3AAC, 0x4B4BC1, 0x4B4CDC, 0x4AD1F3, 0x4B3061,
    0x4B307F, 0x4B2F95, 0x4AA791, 0x4B34B4, 0x522C90,
}
NEW_SECTION_NAME = b".qdcol"

def align_up(v, a): return (v + a - 1) // a * a

class Target:
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        self.pe = pefile.PE(data=bytes(self.data))
        if self.pe.FILE_HEADER.Machine != pefile.MACHINE_TYPE["IMAGE_FILE_MACHINE_AMD64"]:
            raise RuntimeError("只支持 AMD64 Q-Dir")
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.text = next(s for s in self.pe.sections if s.Name.rstrip(b"\0") == b".text")
        self.tva, self.toff = self.text.VirtualAddress, self.text.PointerToRawData
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.md.skipdata = True
    def va2off(self, va):
        off = va - self.base - self.tva + self.toff
        if not 0 <= off < len(self.data): raise RuntimeError("VA 不在文件中: %#x" % va)
        return off
    def verify(self, want_max=OLD_MAX):
        bad = []
        for va, old in LOOP_SITES:
            cur = bytes(self.data[self.va2off(va):self.va2off(va) + len(old)])
            want = old if want_max == OLD_MAX else (old[:2] + bytes([want_max]) if len(old) == 3 else old[:1] + bytes([want_max, 0, 0, 0]))
            if cur != want: bad.append("%#x: %s != %s" % (va, cur.hex(), want.hex()))
        return bad
    def scan_array_refs(self):
        seg = bytes(self.data[self.toff:self.toff + self.text.SizeOfRawData])
        found = {}
        lo, hi = ARRAY_RVA, ARRAY_RVA + ARRAY_STRIDE
        for i in range(len(seg) - 4):
            disp = struct.unpack_from("<i", seg, i)[0]
            for k in range(4, 9):
                tgt = self.tva + i + k + disp
                if not lo <= tgt < hi: continue
                for s in range(max(0, i - 10), i + 1):
                    va_s = self.base + self.tva + s
                    if va_s not in EXPECTED_REF_VAS: continue
                    L = i + k - s
                    if L <= 0 or L > 15: continue
                    for ins in self.md.disasm(seg[s:s + L], va_s, 1):
                        if ins.size == L and "[rip" in ins.op_str and ins.address + ins.size + disp - self.base == tgt:
                            found[va_s] = (self.toff + i, tgt)
        return found

def add_section(tgt, name, vsize, raw):
    pe, data = tgt.pe, tgt.data
    coff = pe.FILE_HEADER.get_file_offset(); nsec_off = coff + 2
    opt = pe.OPTIONAL_HEADER.get_file_offset(); sec_tbl = opt + pe.FILE_HEADER.SizeOfOptionalHeader
    new_hdr = sec_tbl + pe.FILE_HEADER.NumberOfSections * 40
    if new_hdr + 40 > pe.OPTIONAL_HEADER.SizeOfHeaders or data[new_hdr:new_hdr + 40] != b"\0" * 40:
        raise RuntimeError("PE 头部没有可用节表空间")
    sec_align, file_align = pe.OPTIONAL_HEADER.SectionAlignment, pe.OPTIONAL_HEADER.FileAlignment
    last = max(s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData) for s in pe.sections)
    rva = align_up(last, sec_align)
    data.extend(b"\0" * (align_up(len(data), file_align) - len(data)))
    raw_ptr = len(data); data.extend(raw)
    hdr = struct.pack("<8sIIIIIIHHI", name, vsize, rva, len(raw), raw_ptr, 0, 0, 0, 0, 0xC0000040)
    data[new_hdr:new_hdr + 40] = hdr
    struct.pack_into("<H", data, nsec_off, pe.FILE_HEADER.NumberOfSections + 1)
    struct.pack_into("<I", data, opt + 0x38, align_up(rva + vsize, sec_align))
    return rva

def apply_patch(tgt, new_max, only=None, relocate=True):
    if relocate:
        cap = align_up(new_max * ARRAY_STRIDE, 0x1000)
        new_rva = add_section(tgt, NEW_SECTION_NAME, cap, b"\0" * cap)
        delta = new_rva - ARRAY_RVA
        refs = tgt.scan_array_refs()
        if set(refs) != EXPECTED_REF_VAS:
            raise RuntimeError("数组引用不完整: 缺 %s" % [hex(x) for x in EXPECTED_REF_VAS - set(refs)])
        for _, (disp_off, _) in refs.items():
            old = struct.unpack_from("<i", tgt.data, disp_off)[0]
            struct.pack_into("<i", tgt.data, disp_off, old + delta)
    else:
        cap, new_rva, delta, refs = 0, ARRAY_RVA, 0, {}
    for va, old in (LOOP_SITES if only is None else [LOOP_SITES[i] for i in only]):
        off = tgt.va2off(va)
        tgt.data[off:off + len(old)] = old[:2] + bytes([new_max]) if len(old) == 3 else old[:1] + bytes([new_max, 0, 0, 0])
    # 这是独立于载入/保存上限的运行时样式索引守卫。
    if only is None:
        va, old = RENDER_GUARD
        off = tgt.va2off(va)
        cur = bytes(tgt.data[off:off + len(old)])
        if cur != old and cur != bytes.fromhex("83 7e 18 7f"):
            raise RuntimeError("渲染守卫特征不匹配: %#x = %s" % (va, cur.hex()))
        tgt.data[off:off + len(old)] = old[:3] + bytes([new_max])
        # 原版为 mov ecx, 31；应改为 mov ecx, new_max-1，清理完整扩容区。
        va, old = INIT_CLEAR
        off = tgt.va2off(va)
        cur = bytes(tgt.data[off:off + len(old)])
        if cur != old and cur != (old[:1] + struct.pack("<I", new_max - 1)):
            raise RuntimeError("初始化清理上限特征不匹配: %#x = %s" % (va, cur.hex()))
        tgt.data[off:off + len(old)] = old[:1] + struct.pack("<I", new_max - 1)
    return new_rva, cap, len(refs)

def current_max(t):
    """返回目标文件当前的规则上限：一致则返回值，否则返回 None。"""
    vals = set()
    for va, old in LOOP_SITES:
        cur = bytes(t.data[t.va2off(va):t.va2off(va) + len(old)])
        vals.add(cur[2] if len(old) == 3 else cur[1])
    return vals.pop() if len(vals) == 1 else None

def has_patch_section(t, name=NEW_SECTION_NAME):
    return any(s.Name.rstrip(b"\0") == name for s in t.pe.sections)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None); ap.add_argument("--exe", default=EXE_NAME)
    ap.add_argument("--max", type=int, default=127); ap.add_argument("--out", default=None)
    ap.add_argument("--in-place", action="store_true", help="就地覆盖 --exe（默认输出到 <name>_patched.exe）")
    ap.add_argument("--check", action="store_true"); ap.add_argument("--restore", action="store_true")
    ap.add_argument("--only", default=None); ap.add_argument("--no-reloc", action="store_true")
    ap.add_argument("--patch-render-loop", action="store_true",
                    help="调试用：将颜色应用循环中的 0x20 步长上限改为 --max")
    a = ap.parse_args()
    if a.dir:
        d = a.dir
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        d = base
        for cand in (base, os.path.join(base, "Q-Dir")):
            if os.path.isfile(os.path.join(cand, a.exe)):
                d = cand; break
    exe = os.path.join(d, a.exe); orig = exe + ".orig"
    if a.restore:
        if not os.path.isfile(orig): sys.exit("没有找到备份 %s，无法还原" % orig)
        shutil.copy2(orig, exe); print("已还原", exe); return
    if not 32 <= a.max <= 127: sys.exit("--max 必须在 32~127（cmp r32,imm8 有符号立即数上限 127）")
    t = Target(exe)
    if a.check:
        r = t.scan_array_refs()
        cm = current_max(t)
        print("文件: %s" % exe)
        print("上限点 %d 处，当前一致值: %s" % (len(LOOP_SITES), "0x%02x (%d)" % (cm, cm) if cm is not None else "不一致"))
        print("数组引用 %d/%d，扩容节 %s: %s" % (len(r), len(EXPECTED_REF_VAS),
              NEW_SECTION_NAME.decode(), "已存在" if has_patch_section(t) else "无"))
        if cm is None:
            print("结论: 不适用（五处上限值不一致，可能不是支持的目标版本）"); return 1
        if cm == OLD_MAX and set(r) == EXPECTED_REF_VAS and not has_patch_section(t):
            print("结论: 原版（上限 32），可以打补丁"); return 0
        if cm != OLD_MAX:
            print("结论: 已打补丁（上限 %d），无需重复打补丁；重复打会因特征不匹配而报错" % cm)
            return 0
        print("结论: 不适用（引用或节状态异常）"); return 1
    if not os.path.isfile(orig): shutil.copy2(exe, orig)
    only = [int(x) for x in a.only.split(",")] if a.only else None
    try:
        nr, cap, refs = apply_patch(t, a.max, only, not a.no_reloc)
    except RuntimeError as e:
        sys.exit("打补丁失败: %s\n（原因通常是目标不是原版 Q-Dir.exe，或版本不匹配）" % e)
    if a.out: out = a.out
    elif a.in_place: out = exe
    else:
        root, ext = os.path.splitext(exe); out = root + "_patched" + ext
    open(out, "wb").write(t.data)
    print("原版备份: %s" % orig)
    print("打补丁完成: %s, 数组 RVA %#x, 上限 32->%d, 搬迁引用 %d, 节容量 %d" % (out, nr, a.max, refs, cap))
    if only is None:
        chk = Target(out)
        issues = chk.verify(a.max)
        for va, old, label, want in [
            (RENDER_GUARD[0], RENDER_GUARD[1], "渲染守卫", RENDER_GUARD[1][:3] + bytes([a.max])),
            (INIT_CLEAR[0], INIT_CLEAR[1], "初始化清理", INIT_CLEAR[1][:1] + struct.pack("<I", a.max - 1)),
        ]:
            cur = bytes(chk.data[chk.va2off(va):chk.va2off(va) + len(old)])
            if cur != want: issues.append("%s %#x = %s" % (label, va, cur.hex()))
        print("复检:", "通过" if not issues else "失败: " + "; ".join(issues))
if __name__ == "__main__": main()
```
