#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q-Dir Color Filter 32 条上限补丁

针对 Q-Dir 12.77 x64：
* [Filter2] 规则对象数组位于 RVA 0x1544F0，单项 0x20 字节；
* 规则计数位于 RVA 0x15447C；
* 载入/保存/解析路径的五个 0x20 常量改为新的上限；
* 原数组后方 RVA 0x1548F0 是 Q-Dir 的对象管理哨兵，不是颜色数组的一部分，
  因此迁移颜色数组时不能把它覆盖掉。

目标文件无需手动指定：脚本会自动在自身目录、父目录、兄弟目录（Q-Dir /
Q-Dir_Portable_x64 / x64 / x84 等）中搜索 Q-Dir*.exe、Q-Dir-x64.exe、
Q-Dir-x84.exe 等各种命名，按命名 + 位数 + 目录位置打分后自动挑选。

补丁默认生成可回滚的副本，并校验 PE 特征。
"""
import argparse, fnmatch, os, shutil, struct, sys, time
try:
    import pefile
except ImportError:
    sys.exit("[x] 缺少依赖 pefile，请先执行: pip install pefile")
try:
    import capstone
except ImportError:
    sys.exit("[x] 缺少依赖 capstone，请先执行: pip install capstone")

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

# ---------------------------------------------------------------- 自动搜索
# 默认匹配模式（不区分大小写），覆盖 Q-Dir.exe / Q-Dir-x64.exe / Q-Dir-x84.exe 等
EXE_GLOBS = ("Q-Dir*.exe", "QDir*.exe")
# 常见正式命名的加分值
NAME_SCORE = {
    "q-dir.exe": 100, "q-dir-x64.exe": 92, "q-dir-x84.exe": 90,
    "q-dir-x86.exe": 86, "q-dir64.exe": 84, "q-dir32.exe": 82,
    "qdir.exe": 78, "qdir64.exe": 76, "qdir-x64.exe": 76,
}
# 命中这些词的多半是备份/补丁产物，降权处理
NAME_PENALTY_TOKENS = (
    "patched", "_bak", "backup", "备份", "orig", "待删除", "副本", "copy",
    "_bis", "_max", "_reloc", "_slack", "_verify", "_test", "_old",
)
# 扫描时默认跳过的目录关键字（补丁备份目录里通常有一大堆历史 exe）
SKIP_DIR_TOKENS = ("备份", "待删除", "backup", "_bak", ".git", "__pycache__",
                   "node_modules", "$recycle.bin", "system volume information")
SKIP_DIR_NAMES = {"windows", "program files", "program files (x86)", "appdata"}
# 小于该体积的 exe 视为无关文件（Q-Dir 主程序远大于此）
MIN_EXE_SIZE = 200 * 1024

MACHINE_NAME = {0x8664: "x64", 0x014C: "x86", 0xAA64: "ARM64", 0x01C4: "ARMv7"}

# ---------------------------------------------------------------- 输出辅助
def _init_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_init_stdout()

def _want_color():
    if os.environ.get("QDIR_COLOR") == "1":
        return True
    if os.environ.get("QDIR_COLOR") == "0":
        return False
    return sys.stdout.isatty() and os.name != "nt"

USE_COLOR = _want_color()
QUIET = False
_COLORS = {"info": "", "ok": "\033[32m", "warn": "\033[33m", "err": "\033[31m",
           "step": "\033[36m", "dim": "\033[2m", "hl": "\033[1m"}
_ICONS = {"info": "[i]", "ok": "[OK]", "warn": "[!]", "err": "[x]",
          "step": "[>]", "dim": "   ", "hl": "[*]"}

def set_color(on):
    global USE_COLOR
    USE_COLOR = bool(on)

def log(msg="", level="info", indent=0):
    if QUIET and level in ("info", "dim", "step"):
        return
    pad = " " * indent
    if level == "raw":
        print(pad + msg if pad else msg)
        return
    icon = _ICONS.get(level, "[i]")
    line = "%s%s %s" % (pad, icon, msg) if msg else pad + icon
    if USE_COLOR and _COLORS.get(level):
        line = _COLORS[level] + line + "\033[0m"
    print(line, flush=True)

def hr(ch="-", n=66):
    if QUIET:
        return
    log(ch * n, "dim")

def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.0f %s" % (n, unit) if unit == "B" else "%.2f %s" % (n, unit)
        n /= 1024.0

class Steps:
    """打印带序号的步骤标题，例如 [步骤 2] 载入并校验 PE。"""
    def __init__(self):
        self.n = 0
    def __call__(self, title):
        self.n += 1
        hr()
        log("步骤 %d: %s" % (self.n, title), "step")
        hr()

# ---------------------------------------------------------------- PE 工具
def read_pe_arch(path):
    """不依赖 pefile 读取 PE 位数，用于候选文件预览。"""
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"MZ":
                return "非 PE"
            f.seek(0x3C)
            pe_off = struct.unpack("<I", f.read(4))[0]
            f.seek(pe_off)
            if f.read(4) != b"PE\0\0":
                return "非 PE"
            machine = struct.unpack("<H", f.read(2))[0]
            return MACHINE_NAME.get(machine, "未知(%#x)" % machine)
    except Exception:
        return "读取失败"

def default_search_roots(script_dir):
    """脚本目录 -> 当前目录 -> 父目录 -> 父目录下的 Q-Dir 相关子目录。"""
    roots, seen = [], set()

    def add(p):
        if not p or not os.path.isdir(p):
            return
        rp = os.path.normcase(os.path.abspath(p))
        if rp not in seen:
            seen.add(rp)
            roots.append(os.path.abspath(p))

    add(script_dir)
    add(os.getcwd())
    parent = os.path.dirname(os.path.abspath(script_dir))
    add(parent)
    for base in (os.path.abspath(script_dir), parent):
        if not base:
            continue
        for sub in ("Q-Dir", "Q-Dir_Portable_x64", "Q-Dir_Portable",
                    "Q-Dir_x64", "Q-Dir_x84", "x64", "x84", "bin", "Portable"):
            add(os.path.join(base, sub))
        try:
            subs = os.listdir(base)
        except OSError:
            subs = []
        for name in subs:
            low = name.lower()
            if "q-dir" in low or "qdir" in low:
                p = os.path.join(base, name)
                if os.path.isdir(p):
                    add(p)
                    add(os.path.join(p, "Q-Dir"))
    return roots

def is_skipped_dir(name):
    low = name.lower()
    if low.startswith("."):
        return True
    if low in SKIP_DIR_NAMES:
        return True
    return any(tok in low for tok in SKIP_DIR_TOKENS)

def name_matches(name, patterns):
    low = name.lower()
    return any(fnmatch.fnmatch(low, p.lower()) for p in patterns)

def score_candidate(path, root_index, depth):
    name = os.path.basename(path).lower()
    score = NAME_SCORE.get(name, 50)
    if any(tok in name for tok in NAME_PENALTY_TOKENS):
        score -= 45
    arch = read_pe_arch(path)
    if arch == "x64":
        score += 30          # 本补丁只支持 AMD64，优先挑 64 位
    elif arch == "x86":
        score -= 25
    score -= min(depth, 5) * 3   # 越浅越可能是正式安装目录
    return score, arch

def find_candidates(roots, patterns, depth=3, include_backup=False, log_fn=log):
    """在给定根目录中按深度限制搜索匹配的 exe，返回按得分排序的候选列表。"""
    found, skipped = [], []
    for ri, root in enumerate(roots):
        root = os.path.abspath(root)
        base_depth = root.rstrip("\\/").count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root):
            cur_depth = dirpath.rstrip("\\/").count(os.sep) - base_depth
            if not include_backup:
                keep = []
                for d in dirnames:
                    if is_skipped_dir(d):
                        skipped.append(os.path.join(dirpath, d))
                    else:
                        keep.append(d)
                dirnames[:] = keep
            if cur_depth >= depth:
                dirnames[:] = []
            for fn in filenames:
                if not fn.lower().endswith(".exe"):
                    continue
                if not name_matches(fn, patterns):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                if st.st_size < MIN_EXE_SIZE:
                    continue
                score, arch = score_candidate(full, ri, cur_depth)
                found.append({
                    "path": full, "name": fn, "size": st.st_size,
                    "mtime": st.st_mtime, "arch": arch, "score": score,
                    "depth": cur_depth, "root": ri,
                })
    found.sort(key=lambda c: (-c["score"], c["root"], c["depth"], -c["mtime"]))
    # 去重（同一文件可能从多个根目录被搜到）
    uniq, seen = [], set()
    for c in found:
        key = os.path.normcase(os.path.abspath(c["path"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    if log_fn and skipped:
        log_fn("已跳过 %d 个备份/系统目录（--include-backup 可关闭）" % len(skipped), "dim", 2)
    return uniq

def print_candidates(cands, picked=None):
    log("共找到 %d 个候选文件：" % len(cands), "info", 2)
    for i, c in enumerate(cands, 1):
        mark = "  <= 已选中" if picked is not None and i == picked else ""
        log("[%d] %s" % (i, c["path"]), "hl" if mark else "dim", 4)
        log("%s | %s | 修改时间 %s | 得分 %d%s" % (
            human_size(c["size"]), c["arch"],
            time.strftime("%Y-%m-%d %H:%M", time.localtime(c["mtime"])),
            c["score"], mark), "dim", 7)
    if len(cands) > 1:
        log("如需指定其它候选，使用 --pick N（N 为上面方括号中的序号）"
            " 或 --exe <完整路径>", "dim", 4)

def resolve_exe(a, script_dir):
    """解析目标 exe：显式路径 > 显式目录 > 自动搜索。返回 (路径, 候选列表, 选中序号)。"""
    name_arg = a.exe
    looks_like_path = (os.path.isabs(name_arg)
                       or os.sep in name_arg
                       or (os.altsep and os.altsep in name_arg))
    if looks_like_path:
        if os.path.isfile(name_arg):
            log("使用命令行指定的文件: %s" % os.path.abspath(name_arg), "ok", 2)
            return os.path.abspath(name_arg), [], 0
        sys.exit("[x] 指定的文件不存在: %s" % os.path.abspath(name_arg))

    # 未带路径：按名称（支持通配符）在若干根目录中搜索
    patterns = tuple(EXE_GLOBS) if name_arg == EXE_NAME else (name_arg,)
    if a.dir:
        roots = [os.path.abspath(a.dir)]
    else:
        roots = default_search_roots(script_dir)
        for extra in (a.search_dir or []):
            p = os.path.abspath(extra)
            if p not in roots:
                roots.append(p)

    log("搜索根目录 (%d):" % len(roots), "info", 2)
    for r in roots:
        log("- %s" % r, "dim", 4)
    log("匹配模式: %s | 目录深度: %d | 最小体积: %s" % (
        ", ".join(patterns), a.depth, human_size(MIN_EXE_SIZE)), "dim", 2)

    cands = find_candidates(roots, patterns, a.depth, a.include_backup)
    if not cands:
        hr()
        log("没有找到任何匹配的 Q-Dir 可执行文件", "err")
        log("可以试试（任选其一）：", "warn", 2)
        log("1) --search-dir <目录>  追加一个搜索根目录（可重复指定）", "warn", 4)
        log("2) --depth 5            加大搜索深度（当前 %d）" % a.depth, "warn", 4)
        log("3) --include-backup     连备份目录一起搜索", "warn", 4)
        log("4) --exe <完整路径>     直接给出 exe 路径", "warn", 4)
        log("5) --guide              查看完整使用指引", "warn", 4)
        sys.exit(2)

    if a.pick:
        if not 1 <= a.pick <= len(cands):
            sys.exit("[x] --pick %d 超出范围（共 %d 个候选）" % (a.pick, len(cands)))
        idx = a.pick
    else:
        idx = 1
    print_candidates(cands, idx)
    chosen = cands[idx - 1]
    log("自动选择: %s" % chosen["path"], "ok", 2)
    if chosen["arch"] != "x64":
        log("警告: 该文件是 %s，本补丁只支持 AMD64 (x64) 版本" % chosen["arch"], "warn", 2)
    return chosen["path"], cands, idx

def align_up(v, a): return (v + a - 1) // a * a

class Target:
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        self.pe = pefile.PE(data=bytes(self.data))
        if self.pe.FILE_HEADER.Machine != pefile.MACHINE_TYPE["IMAGE_FILE_MACHINE_AMD64"]:
            raise RuntimeError("只支持 AMD64 Q-Dir，当前文件 Machine=%#x" % self.pe.FILE_HEADER.Machine)
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

# ---------------------------------------------------------------- 内置使用指引
GUIDE_TEXT = """
=================================================================
 Q-Dir 颜色过滤器扩容补丁 · 使用指引（脚本内置，--guide 可随时查看）
=================================================================

【这个工具做什么】
  把 Q-Dir 颜色过滤器写死的 32 条规则上限提升到最多 127 条：
  新建 .qdcol 区段搬迁规则数组 -> 改 5 处上限常量 -> 改渲染守卫与启动清理
  上限 -> 重定位 17 处数组引用 -> 写盘后自动复检。
  适用：Q-Dir 12.77 x64（仅 AMD64）。其它版本会因特征不匹配被拒绝执行。

【一、快速开始】
  1) python qdir_colorfilter_unlimit.py --check     # 先看能不能打（不改文件）
  2) python qdir_colorfilter_unlimit.py             # 打补丁，输出 <name>_patched.exe
  3) 退出 Q-Dir，把 _patched.exe 覆盖到安装目录，启动验证 >32 条规则
  4) 出问题：python qdir_colorfilter_unlimit.py --restore
  想一步到位替换原文件：加 --in-place（会先备份 .orig）

【二、它怎么自动找 Q-Dir】
  搜索根目录：脚本目录 -> 当前目录 -> 父目录 -> 父目录下名字含 q-dir/qdir 的
  子目录（Q-Dir、Q-Dir_Portable_x64、x64、x84、bin、Portable 等），默认深 3 层。
  匹配命名：Q-Dir*.exe / QDir*.exe（不区分大小写），即 Q-Dir.exe、Q-Dir-x64.exe、
  Q-Dir-x84.exe、QDir.exe 等都能找到；小于 200 KB 的 exe 忽略。
  多个候选按得分排序，第一名自动选中：
      Q-Dir.exe +100 | Q-Dir-x64 92 | Q-Dir-x84 90 | Q-Dir64 84 | 其它 Q-Dir* 50
      名字含 patched/bak/backup/备份/orig/待删除/副本/copy -> -45
      x64 +30 | x86 -25 | 每深一层 -3 | 同分取修改时间新的
  默认跳过含 备份/待删除/backup/.git/node_modules 等关键字的目录
  （--include-backup 可关闭）。

【三、常用参数】
  目标定位：--exe <名字|完整路径>  --dir <目录>  --search-dir <目录>(可重复)
            --depth <N>  --pick <N>  --list  --include-backup
  补丁参数：--max <32..127>(默认127)  --out <路径>  --in-place
            --check  --restore  --force  --no-reloc  --only 0,1
  输出控制：--quiet  --color / --no-color  --guide  --help

【四、典型场景】
  --list                         只看找到哪些 exe，不做任何修改
  --pick 2                       自动选错了，改用第 2 个候选
  --exe "D:/Tools/Q-Dir-x64.exe" 直接给完整路径，跳过搜索
  --search-dir "D:/Tools" --depth 5    Q-Dir 装在别处时扩大搜索
  --max 64                       只扩到 64 条
  --max 64 --out "D:/Temp/Q-Dir_64.exe"   指定输出位置
  --restore                      用 .orig 还原

【五、输出与退出码】
  [i] 信息  [OK] 成功  [!] 警告  [x] 错误  [>] 步骤  [*] 选中的候选
  步骤 1 定位 exe / 2 校验 PE / 3 检查状态 / 4 备份 / 5 应用补丁 / 6 写盘 / 7 复检
  退出码：0 成功   1 载入失败/预检失败/打补丁失败/复检失败
          2 参数非法或没找到候选 exe   130 用户中断

【六、备份与回滚】
  首次打补丁自动备份 <exe>.orig（不会被二次覆盖）。
  回滚：--restore，或手工 copy /Y "Q-Dir.exe.orig" "Q-Dir.exe"。

【七、常见问题】
  Q 没有找到任何候选？  依次试 --search-dir / --depth 5 / --include-backup / --exe 完整路径
  Q 提示已打补丁？      当前上限不是 32，先 --restore；确需强加 --force
  Q 提示只支持 AMD64？  选中的是 32 位版本，换 x64 的 exe 或 --pick 换候选
  Q 提示文件被占用？    完全退出 Q-Dir 再写；便携版别放 Program Files
  Q 上限能超过 127 吗？ 不能，代码是 cmp r32,imm8 有符号立即数
  Q 中文乱码？          执行 chcp 65001，或加 --no-color

【八、注意】
  --force / --only / --no-reloc 是调试开关，正式补补丁不要用。
  换 Q-Dir 版本后要用新版本的原版 exe 重打，旧的 .orig / _patched 不能混用。

  完整图文说明见同目录：Q-Dir颜色过滤器扩容_使用指南.md
  技术实现细节见同目录：qdir_colorfilter_unlimit.md
"""

def print_guide():
    for line in GUIDE_TEXT.strip("\n").splitlines():
        print(line, flush=True)

def build_parser():
    ap = argparse.ArgumentParser(
        description="Q-Dir 颜色过滤器 32 条上限补丁（自动搜索 Q-Dir.exe / Q-Dir-x64.exe / Q-Dir-x84.exe 等）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s                        自动搜索并打补丁，输出 <name>_patched.exe\n"
            "  %(prog)s --check                只检查当前状态，不修改任何文件\n"
            "  %(prog)s --list                 只列出找到的候选 exe\n"
            "  %(prog)s --guide                打印完整使用指引（新手先看这个）\n"
            "  %(prog)s --pick 2               使用搜索结果中的第 2 个候选\n"
            "  %(prog)s --max 64 --in-place    就地覆盖（会先备份 .orig）\n"
            "  %(prog)s --restore              用 .orig 还原\n"
        ))
    g = ap.add_argument_group("目标定位")
    g.add_argument("--exe", default=EXE_NAME,
                   help="目标文件名（支持通配符）或完整路径；默认自动搜索 %s 系列" % EXE_NAME)
    g.add_argument("--dir", default=None, help="把搜索范围限定在该目录内")
    g.add_argument("--search-dir", action="append", metavar="DIR",
                   help="追加一个搜索根目录，可重复指定")
    g.add_argument("--depth", type=int, default=3, help="搜索目录深度，默认 3")
    g.add_argument("--pick", type=int, default=None, metavar="N",
                   help="指定使用候选列表中的第 N 个文件")
    g.add_argument("--include-backup", action="store_true",
                   help="搜索时不要跳过备份/系统目录")
    g.add_argument("--list", action="store_true", help="只列出候选 exe 并退出")

    p = ap.add_argument_group("补丁参数")
    p.add_argument("--max", type=int, default=127,
                   help="新的规则上限，32~127，默认 127")
    p.add_argument("--out", default=None, help="输出文件路径")
    p.add_argument("--in-place", action="store_true",
                   help="就地覆盖目标 exe（默认输出到 <name>_patched.exe）")
    p.add_argument("--no-reloc", action="store_true",
                   help="不把颜色数组搬迁到新区段（容量受限，仅调试用）")
    p.add_argument("--only", default=None,
                   help="只改五个上限点中的指定几项，例如 --only 0,1（调试用）")
    p.add_argument("--force", action="store_true",
                   help="跳过“已打补丁/版本不匹配”的预检拦截")
    p.add_argument("--check", action="store_true", help="只检查目标文件状态")
    p.add_argument("--restore", action="store_true", help="用 .orig 备份还原目标文件")

    o = ap.add_argument_group("输出控制")
    o.add_argument("--quiet", action="store_true", help="只输出关键结果与错误")
    o.add_argument("--guide", action="store_true",
                   help="打印完整使用指引（快速开始/搜索规则/场景/FAQ）后退出")
    o.add_argument("--color", dest="color", action="store_true", default=None,
                   help="强制开启彩色输出")
    o.add_argument("--no-color", dest="color", action="store_false",
                   help="关闭彩色输出")
    return ap

def main():
    ap = build_parser()
    a = ap.parse_args()
    if a.color is not None:
        set_color(a.color)
    global QUIET
    QUIET = a.quiet
    if a.guide:
        print_guide()
        return 0
    if not 32 <= a.max <= 127:
        log("--max 必须在 32~127（cmp r32,imm8 有符号立即数上限 127）", "err")
        return 2

    log("=" * 66, "dim")
    log("Q-Dir 颜色过滤器上限补丁工具  (目标: Q-Dir 12.77 x64)")
    log("=" * 66, "dim")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    st = Steps()

    st("定位 Q-Dir 可执行文件")
    exe, cands, picked = resolve_exe(a, script_dir)
    orig = exe + ".orig"

    if a.list:
        log("已按 --list 要求仅列出候选，未做任何修改", "ok")
        return 0

    if a.restore:
        st("还原")
        if not os.path.isfile(orig):
            log("没有找到备份 %s，无法还原" % orig, "err")
            return 1
        shutil.copy2(orig, exe)
        log("已还原: %s  <-  %s" % (exe, orig), "ok")
        return 0

    st("载入并校验 PE")
    log("目标文件: %s (%s)" % (exe, human_size(os.path.getsize(exe))), "info", 2)
    try:
        t = Target(exe)
    except Exception as e:
        log("载入失败: %s" % e, "err", 2)
        log("该文件可能不是 Q-Dir 主程序，或位数/版本不受支持；"
            "可用 --pick N 或 --exe <路径> 换一个候选", "info", 2)
        if len(cands) > 1:
            print_candidates(cands, picked)
        return 1
    log("PE64 校验通过 | ImageBase %#x | .text RVA %#x (原始偏移 %#x, %s)" % (
        t.base, t.tva, t.toff, human_size(t.text.SizeOfRawData)), "ok", 2)

    st("检查当前补丁状态")
    r = t.scan_array_refs()
    cm = current_max(t)
    sec = has_patch_section(t)
    log("上限点 %d 处，当前一致值: %s" % (
        len(LOOP_SITES), "0x%02x (%d)" % (cm, cm) if cm is not None else "不一致（可能不是支持的目标版本）"),
        "info" if cm is not None else "warn", 2)
    log("数组引用 %d/%d | 扩容节 %s: %s" % (
        len(r), len(EXPECTED_REF_VAS), NEW_SECTION_NAME.decode(),
        "已存在" if sec else "无"), "info" if len(r) == len(EXPECTED_REF_VAS) else "warn", 2)

    if a.check:
        if cm is None:
            log("结论: 不适用（五处上限值不一致，可能不是支持的目标版本）", "err", 2)
            return 1
        if cm == OLD_MAX and set(r) == EXPECTED_REF_VAS and not sec:
            log("结论: 原版（上限 %d），可以打补丁" % OLD_MAX, "ok", 2)
            log("下一步: 直接运行本脚本即可，或加 --max N 指定上限", "dim", 2)
            return 0
        if cm != OLD_MAX:
            log("结论: 已打补丁（上限 %d），无需重复打补丁；重复打会因特征不匹配而报错" % cm, "warn", 2)
            log("如需还原: %s --restore" % os.path.basename(__file__), "dim", 2)
            return 0
        log("结论: 不适用（引用或节状态异常）", "err", 2)
        return 1

    if a.only is None and not a.force:
        if cm is None:
            log("预检失败: 五处上限值不一致，目标文件很可能不是 Q-Dir 12.77 x64", "err", 2)
            log("确认无误可加 --force 强制执行（风险自负）", "info", 2)
            return 1
        if cm != OLD_MAX:
            log("预检失败: 当前上限已是 %d（原版应为 %d），文件可能已打过补丁" % (cm, OLD_MAX), "err", 2)
            log("请先 --restore 还原，或加 --force 强制执行", "info", 2)
            return 1

    st("备份原文件")
    if os.path.isfile(orig):
        log("已存在备份，保留不覆盖: %s" % orig, "info", 2)
    else:
        shutil.copy2(exe, orig)
        log("已创建备份: %s" % orig, "ok", 2)

    st("应用补丁")
    only = None
    if a.only:
        try:
            only = [int(x) for x in a.only.split(",")]
            assert all(0 <= i < len(LOOP_SITES) for i in only)
        except Exception:
            log("--only 取值非法: %r（应为 0~%d 的逗号分隔序号）" % (a.only, len(LOOP_SITES) - 1), "err")
            return 2
    log("目标上限: %d -> %d | 数组搬迁: %s%s" % (
        OLD_MAX, a.max, "否" if a.no_reloc else "是",
        " | 仅改上限点 %s" % only if only else ""), "info", 2)
    try:
        nr, cap, refs = apply_patch(t, a.max, only, not a.no_reloc)
    except RuntimeError as e:
        log("打补丁失败: %s" % e, "err", 2)
        log("原因通常是目标不是原版 Q-Dir.exe，或版本不匹配；原文件未被修改", "info", 2)
        return 1

    st("写出结果")
    if a.out:
        out = a.out
    elif a.in_place:
        out = exe
    else:
        root, ext = os.path.splitext(exe)
        out = root + "_patched" + ext
    try:
        with open(out, "wb") as f:
            f.write(t.data)
    except PermissionError:
        log("写入失败: %s（文件被占用或只读，请先关闭 Q-Dir）" % out, "err", 2)
        return 1
    log("输出文件: %s (%s)" % (out, human_size(os.path.getsize(out))), "ok", 2)
    log("数组 RVA %#x | 上限 %d -> %d | 搬迁引用 %d | 新区段容量 %d" % (
        nr, OLD_MAX, a.max, refs, cap), "info", 2)
    if not a.in_place:
        log("原文件未被修改，仍可通过 %s 还原" % os.path.basename(orig), "dim", 2)

    if only is None:
        st("复检输出文件")
        chk = Target(out)
        issues = chk.verify(a.max)
        for va, old, label, want in [
            (RENDER_GUARD[0], RENDER_GUARD[1], "渲染守卫", RENDER_GUARD[1][:3] + bytes([a.max])),
            (INIT_CLEAR[0], INIT_CLEAR[1], "初始化清理", INIT_CLEAR[1][:1] + struct.pack("<I", a.max - 1)),
        ]:
            cur = bytes(chk.data[chk.va2off(va):chk.va2off(va) + len(old)])
            if cur != want:
                issues.append("%s %#x = %s" % (label, va, cur.hex()))
        if issues:
            log("复检失败: %s" % "; ".join(issues), "err", 2)
            return 1
        log("复检通过：五处上限点 + 渲染守卫 + 初始化清理全部符合 %d" % a.max, "ok", 2)

    hr("=")
    if a.in_place:
        log("完成：%s 已就地打补丁，可直接运行 Q-Dir 验证" % out, "ok")
    else:
        log("完成：请把 %s 复制覆盖到 Q-Dir 安装目录后运行验证" % os.path.basename(out), "ok")
        log("（覆盖前记得先退出 Q-Dir；出问题时用 %s 还原）" % os.path.basename(orig), "dim", 2)
    hr("=")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        log("已取消（用户中断）", "warn")
        sys.exit(130)
