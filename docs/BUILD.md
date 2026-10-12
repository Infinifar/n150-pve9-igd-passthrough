# 从公开源码构建 N150 初始化 ROM

最终 ROM 是本案例的定制产物，QEMU 和 PVE OVMF 包仍为官方版本。构建的是小型初始化驱动，不是重新构建整个 OVMF，也不是替换 QEMU。

## 固定来源

| 内容 | 版本 / 来源 |
| --- | --- |
| EDK2 | `edk2-stable202608`，提交 `2970e5699ba6267f3384ffab20f96647578aebc8` |
| MIPI Sys-T | `370b5944c046bab043dd8b133727b2135af7747a` |
| Brotli | `e230f474b87134e8c6c85b630084c612057f253e` |
| Intel 原始驱动 | [ECI 3.3 KVM 文档](https://eci.intel.com/docs/3.3/components/kvm-hypervisor.html)发布的两份补丁 |
| 本地适配 | [intel-n150-gen12.patch](../source/intel-n150-gen12.patch)，仅设备 ID `46d4` |

Intel 原始补丁下载入口：

- [0001：OpRegion/VBT 等头文件](https://eci.intel.com/docs/3.3/_downloads/144142a10064c51605cb1e3affe4f0b8/0001-OvmfPkg-Add-OpRegion-and-VBT-header-definition.patch)
- [0002：IgdAssignmentDxe](https://eci.intel.com/docs/3.3/_downloads/b3b459438ddaa611a01e6746b231963d/0002-OvmfPkg-add-IgdAssignmentDxe.patch)

原始署名与许可保留。`prepare-igd-source.py` 只提取补丁新增的四个文件，不把历史整套 OvmfPkg 构建描述套用到新版 EDK2；随后应用已归档的 N150 差异并复制最小 DSC。

## 构建环境

建议使用独立 x86_64 Debian/Ubuntu 构建机，避免为编译在 PVE 上安装一套开发工具。需要 `git`、`gcc`、`make`、`python3`、`nasm` 和 `uuid-dev`；例如在构建机执行：

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends git gcc make python3 nasm uuid-dev
git clone https://github.com/Infinifar/n150-pve9-igd-passthrough.git
cd n150-pve9-igd-passthrough
bash scripts/build-rom.sh
```

脚本从官方 EDK2 Git 仓库取固定提交，只初始化上述两个所需子模块，并验证三个 HEAD。默认工作目录为 `build/`，可用 `--work-dir /absolute/build/path` 指定。脚本不会安装系统包、替换 OVMF 或把 ROM 安装到 PVE。

若已经有固定版本的 EDK2 Git 工作树和两个子模块：

```bash
bash scripts/build-rom.sh --work-dir /absolute/build/path --edk2-source /absolute/edk2
```

这会在指定 EDK2 树中加入/刷新四个 Intel 文件、N150 适配与最小 DSC，并产生 `Build/IntelIgdInit`。使用专门的干净构建树；脚本拒绝已有 tracked EDK2 改动。不接受缺少 Git 版本信息的解压目录作为该参数。

原案例为避免 PVE 装包，使用已存在的 GCC/make/Python，仅把 nasm、uuid-dev 的 Debian 包下载、解压到隔离目录，并在构建命令的 PATH/include/library path 中使用。归档 ROM 来自那次构建；本仓库把流程改为通用参数，保留相同源码与 X64 / DEBUG / GCC 目标。

## 产物与使用边界

输出到 `WORK_DIR/artifacts/`：

```text
intel-igd-init-gen12-46d4.rom
IgdAssignmentDxe.efi
rom-header.txt
SHA256SUMS
```

构建只编译必要的 EDK2 GenFw/EfiRom 工具、驱动和依赖库。EfiRom 用 `8086:46d4` 封装并检查 EFI/PCIR 头，不包含 IntelGopDriver 或 PlatformGopPolicy。

N150 适配依据 [QEMU 11 的 IGD 实现](https://github.com/qemu/qemu/blob/v11.0.3/hw/vfio/igd.c)以及实际客体寄存器诊断：64 位 Gen11+ BDSM 位于 `0xC0`，仍沿用宿主 GGC/DSM 大小。没有增加显存覆盖值，也没有把该判断推广到其他 GPU。

重新编译可能因 PE 时间戳和工具链产生不同 SHA256。`pve-n150.py` 固定校验仓库归档的已测试 ROM，**不会自动安装你重新编译的产物**。若要测试本地 ROM，另起一次配置备份，给产物使用不同文件名，核对头部和来源后手动设置 romfile；保留原归档以便回滚。

归档 ROM SHA256：

```text
256f9d45b79c79b50ad13d79787edae5af7c6dc830a762110ad6e94f913e0eef
```

GitHub Actions 会运行模拟 PVE 测试、脚本检查、归档 ROM 校验和固定源码构建。CI 构建成功只验证构建流程；硬件结果来自 [实测记录](CASE-STUDY.md)。
