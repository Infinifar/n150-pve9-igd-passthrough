# Intel N150 核显直通：PVE 9.2 / Windows 10

把一次实际成功的配置整理成可复现教程：使用官方 PVE/QEMU，先测最小直通，再根据证据修复 Code 43，最后验证物理显示。

**验证结果：** Intel `8086:46d4`，Windows 错误码 **0**，物理显示 **1920×1080 / 60 Hz**。案例最终内存为 **4 GiB**，保留虚拟显示设备，Secure Boot 开启。

> QEMU 没有替换或修改。成功方案使用了一个基于 Intel 发布源码、针对 N150 适配的初始化 ROM；它属于本仓库的定制固件产物，不是 Intel 官方发布的 N150 ROM。这里只收录初始化驱动，不含专有 Intel GOP。

## 阅读入口

- [完整中文教程](docs/TUTORIAL.zh-CN.md)：宿主机前提、最小直通、Code 43 诊断、分阶段修复、回滚。
- [实际测试过程](docs/CASE-STUDY.md)：每次改变了什么、寄存器如何变化、哪些结论仍有边界。
- [ROM 来源与构建](docs/BUILD.md)：固定版本、适配补丁、重新编译的方法。
- [脚本参考](docs/SCRIPTS.md)：参数、拒绝条件、备份内容。
- [关键配置片段](examples/102.conf.fragment)：不包含磁盘、网络或机器身份信息。

## 验证环境

| 项目 | 本次实测 |
| --- | --- |
| 测试日期 | 2026-10-07，Asia/Shanghai |
| PVE manager | 9.2.21 |
| pve-qemu-kvm | 11.0.3-4，官方包 |
| 内核 | 7.0.14-20-pve |
| pve-edk2-firmware | 4.2026.08-1 |
| 客体固件 / machine | OVMF / pc-q35-11.0 |
| GPU | Intel N150，0000:00:02.0，8086:46d4 |
| 客体系统 / Intel 驱动 | Windows 10 / 32.0.101.7088 |
| 内存 / Balloon | 4096 MiB / balloon: 0 |
| 物理显示 | 1920×1080 / 60 Hz |

这是单台机器上的实测记录。其他 N 系列、其他设备 ID、固件版本或显示输出不能据此视为已验证。IOMMU group 编号应以各自机器为准。

## 快速开始

先读教程前两节，确认 Windows 已能用 OVMF 启动、宿主核显已经绑定 `vfio-pci`，且独占 IOMMU group。脚本不会代替你修改宿主启动参数或强制重新绑定核显。

在 PVE 主机以 root 执行：

```bash
git clone https://github.com/Infinifar/n150-pve9-igd-passthrough.git
cd n150-pve9-igd-passthrough
python3 scripts/pve-n150.py inspect --vmid 102
```

`102` 是案例 VMID，使用时换成你的 VMID。除 `inspect` 外，操作默认只预览；加 `--apply` 才会修改或启动。配置修改要求 VM 已停止。

先正常关闭 Windows，然后只应用 Stage 1：

```bash
qm shutdown 102 --timeout 60
qm status 102                 # 必须显示 stopped
python3 scripts/pve-n150.py stage1 --vmid 102 --apply
python3 scripts/pve-n150.py start --vmid 102 --apply
```

**不要直接连续执行所有修复步骤。** 先检查 Windows 设备管理器与物理屏幕。如果 Stage 1 已正常，就停在这一阶段。若仍有 Code 43，按教程收集 OpRegion/BDSM 证据，再分别测试 ROM 与客体 PCI 地址。

本案例最后的关键配置为：

```text
bios: ovmf
machine: pc-q35-11.0
memory: 4096
balloon: 0
hostpci0: 0000:00:02.0,pcie=1,romfile=intel-igd-init-gen12-46d4.rom
args: -set device.hostpci0.bus=pcie.0 -set device.hostpci0.addr=0x2
```

虚拟 VGA 保留；没有加入 `x-igd-gms`、`x-igd-lpc`、`x-igd-legacy-mode`、`x-vga`，没有直通 `00:1f.3` 音频。

## 仓库内容

```text
scripts/pve-n150.py            预检、分阶段配置、内存、启动、回滚
scripts/inspect-igd-qmp.py     只读检查实际客体 PCI 地址与 IGD 寄存器
scripts/verify-windows.ps1    Windows 显卡、显示分辨率、Secure Boot 检查
scripts/build-rom.sh          编译初始化 ROM，不安装到系统
scripts/prepare-igd-source.py 提取 Intel 原始文件并应用 N150 补丁
source/                      原始 Intel 补丁、N150 补丁、最小 DSC
firmware/                    实测 ROM、SHA256 与来源说明
tests/                       模拟 PVE 的变更与失败场景测试
```

仓库不收录 SSH 凭据、实际完整 VM 配置、内网地址、MAC/UUID、Windows 设备实例路径或原始主机日志。脚本生成的备份和诊断输出保存在使用者自己的机器上。

## 验证与许可

```bash
python3 -m unittest discover -s tests -v
bash -n scripts/build-rom.sh
sha256sum -c firmware/SHA256SUMS
```

历史硬件验证覆盖正常关机再启动、客体显卡状态以及用户对物理显示的确认；不包含宿主机重启或长期压力测试。新整理的自动化脚本采用模拟环境测试，不能把模拟通过等同于在所有硬件上已验证。

本仓库原创脚本及说明采用 [MIT](LICENSE)；Intel 补丁和 ROM 所链接的 EDK2 代码保留各自许可，见 [第三方声明](THIRD_PARTY_NOTICES.md)。
