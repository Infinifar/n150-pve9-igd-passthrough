# N150 在 PVE 9.2 上直通给 Windows 10

目标是让 Windows 直接使用 N150 核显和物理显示输出，同时保留虚拟显示设备用于观察。执行顺序是：**核对宿主前提 → 官方最小直通 → 收集 Code 43 证据 → 单独测试初始化 ROM → 单独调整客体 PCI 地址 → USB 和验收**。

以下 `102` 为案例 VMID。PVE 命令在宿主机以 root 执行；Windows 检查在客体管理员 PowerShell 执行。不要把示例配置文件覆盖到自己的 VM：磁盘、EFI、TPM、网络应沿用各自原配置。

## 1. 宿主机前提与初始检查

BIOS 中启用虚拟化与 VT-d/IOMMU。先确保能通过网络管理 PVE；核显被 VFIO 接管后，宿主不能继续使用它显示自己的控制台。

```bash
pveversion -v
dpkg-query -W pve-qemu-kvm pve-edk2-firmware
dpkg -V pve-qemu-kvm
qm status 102
qm config 102
qm showcmd 102 --pretty
lspci -Dnnk -s 0000:00:02.0
readlink -f /sys/bus/pci/devices/0000:00:02.0/driver
readlink -f /sys/bus/pci/devices/0000:00:02.0/iommu_group
ls -1 /sys/bus/pci/devices/0000:00:02.0/iommu_group/devices
dmesg | rg -i 'DMAR|IOMMU|vfio'
```

没有 `rg` 时最后一条可使用 `grep -Ei`。预期设备 ID 为 `[8086:46d4]`、驱动为 `vfio-pci`，group 内只有 `0000:00:02.0`。本案例是 group 0；其他机器的 group 编号可以不同，重点是成员。

本案例开始时 IOMMU/VFIO 已正确配置，**后续修复没有更改宿主启动参数或驱动绑定**。如果你的机器尚未满足前提，先独立解决这些问题，再进入本教程 Stage 1。不要在 Windows 运行时尝试解除绑定 GPU。

### 尚未启用 IOMMU/VFIO 时的条件性准备

参考 [Proxmox PCI Passthrough 文档](https://pve.proxmox.com/wiki/PCI_Passthrough)。这部分是准备指南，不是本案例实际做过的变更；脚本不会自动执行。

先辨认启动方式：

```bash
proxmox-boot-tool status
cat /proc/cmdline
```

如果尚无 Intel IOMMU 支持，按正在使用的启动器，在现有内核参数中追加 `intel_iommu=on`。使用 GRUB 的机器先备份并编辑 `/etc/default/grub`，再执行 `update-grub`；使用 systemd-boot 的机器先备份并编辑 `/etc/kernel/cmdline`，再执行 `proxmox-boot-tool refresh`。保留原有参数，不同时修改两套配置。

为指定设备配置早期 VFIO 接管时，可在备份原有相关文件后加入：

```text
# /etc/modprobe.d/vfio-n150.conf
options vfio-pci ids=8086:46d4
softdep i915 pre: vfio-pci
```

检查 `/etc/initramfs-tools/modules` 中包含 `vfio`、`vfio_iommu_type1`、`vfio_pci`，然后 `update-initramfs -u -k all`。以上操作可能需要宿主重启，应先正常关闭虚拟机并安排维护时间；重启后重新验证驱动和 IOMMU group。

不要默认加入 ACS override、禁用所有 framebuffer、黑名单全部声卡或替换 QEMU。若日志确实显示 BAR 映射冲突，再单独诊断占用来源。本仓库预检不接受共享 GPU group。

## 2. 备份与客体前提

使用现有、已能正常启动的 **OVMF Windows VM**，具备 EFI 磁盘和 `pc-q35-11.0`。已经用传统 BIOS 安装的 Windows 不能仅靠把 BIOS 字段改成 OVMF 就保证可启动；先完成客体转换或重新创建适合的 VM。

保留虚拟显示设备。本案例没有 `vga:` 字段，PVE 因而添加默认虚拟 VGA；如果你的配置是 `vga: none`，先恢复可用的虚拟显示用于观察。Secure Boot 在本案例始终开启，不需要作为默认修复措施关闭。

手动修改前的最小备份：

```bash
backup_dir="/root/n150-manual-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$backup_dir"
cp /etc/pve/qemu-server/102.conf "$backup_dir/102.conf.before"
qm showcmd 102 --pretty > "$backup_dir/showcmd.before.txt"
```

这里是配置备份，不能替代磁盘/EFI 内容的 VM 备份。使用本仓库脚本时每次写入都有独立检查点，不必另行复制整份案例配置。

## 3. Stage 1：只增加最小 GPU 直通

在 Windows 正常关机后确认 `qm status 102` 为 stopped。先只增加：

```text
hostpci0: 0000:00:02.0,pcie=1
```

用脚本预览、应用，然后启动：

```bash
python3 scripts/pve-n150.py stage1 --vmid 102
python3 scripts/pve-n150.py stage1 --vmid 102 --apply
python3 scripts/pve-n150.py start --vmid 102 --apply
```

对应的手动 GPU 设置为 `qm set 102 --hostpci0 0000:00:02.0,pcie=1`。脚本同时检查版本、IOMMU、VFIO、已有 PCI 设备与自定义参数，避免覆盖原配置。

这一阶段不加 ROM、显存覆盖、LPC/legacy/VGA 兼容参数，不直通音频。先查看设备管理器、驱动版本、物理屏幕，保留启动日志。如果启动失败，收集 `qm showcmd` 和明确错误，先处理这一处问题。

本案例 VM 能启动，但 Intel 显卡报 **Code 43**，因此继续检查；不是所有机器都必然需要下一阶段。

## 4. Code 43：确认 OpRegion 与显存预留

看到 `OpRegion detected on Intel display 46d4` 只说明 QEMU 检测到宿主数据，不能证明客体固件已经完成初始化。

在 VM 运行时，通过只读 QMP 检查：

```bash
python3 scripts/inspect-igd-qmp.py --vmid 102
```

诊断脚本不写客体内存。它定位实际 GPU BDF，再读取 ASLS、Gen11+ BDSM 和 OpRegion 签名。Stage 1 实测：

```text
ASLS / OpRegion: 0
BDSM at 0xC0:  0
```

[QEMU 11 官方 IGD 文档](https://github.com/qemu/qemu/blob/v11.0.3/docs/igd-assign.txt)说明这些区域需要客户机固件建立，并提供了用初始化驱动构造 option ROM 的路径。这里采用外置小型 ROM，继续保留官方 QEMU 和 OVMF 包。

## 5. Stage 2：N150 初始化 ROM

本仓库 ROM 来自 Intel 发布的 IgdAssignmentDxe 源码，增加了只匹配 `8086:46d4` 的适配：把该设备的 BDSM 写入改为 `0xC0` 的两个 DWORD，并允许它在较早测试所用的非 `00:02.0` 地址初始化 DSM。

Intel 原始版本只建立了有效 OpRegion，仍未建立这台 N150 的 BDSM，Code 43 保留。因此教程使用最终 N150 适配版，保留原始源码与差异供核对。详细来源见 [BUILD.md](BUILD.md)。它不含 GOP，不能据此期待物理屏幕在 Windows 驱动加载前显示 UEFI 画面。

正常关闭 VM，核对仓库 ROM 哈希：

```bash
qm shutdown 102 --timeout 60
qm status 102
sha256sum -c firmware/SHA256SUMS
python3 scripts/pve-n150.py rom --vmid 102
python3 scripts/pve-n150.py rom --vmid 102 --apply
python3 scripts/pve-n150.py start --vmid 102 --apply
```

脚本将确切 ROM 安装到 `/usr/share/kvm/intel-igd-init-gen12-46d4.rom`，同时把 hostpci0 更新为：

```text
hostpci0: 0000:00:02.0,pcie=1,romfile=intel-igd-init-gen12-46d4.rom
```

这个阶段暂不改 PCI 地址。重测 Windows 错误码与寄存器。本案例此时 Code 43 已消失，但曾报告物理屏幕花屏/闪屏；因此继续做一次单独的地址测试。

## 6. Stage 3：把客体 GPU 放在 00:02.0

物理地址与客体地址是两个概念。即使传入的是宿主 `0000:00:02.0`，PVE 默认可能把它放在客体 root port 后面的 `01:00.0`。

本次使用 QEMU 原生参数覆盖该设备的位置，保留虚拟 VGA：

```bash
qm shutdown 102 --timeout 60
qm status 102
python3 scripts/pve-n150.py root-pci --vmid 102
python3 scripts/pve-n150.py root-pci --vmid 102 --apply
python3 scripts/pve-n150.py start --vmid 102 --apply
python3 scripts/inspect-igd-qmp.py --vmid 102
```

写入的配置：

```text
args: -set device.hostpci0.bus=pcie.0 -set device.hostpci0.addr=0x2
```

脚本在存在其他自定义 `args` 时会拒绝覆盖。`qm showcmd` 可能仍先列出原 root port 的 `-device`，后面的 `-set` 才覆盖位置，所以必须用运行时 `query-pci` 验证实际 BDF。

本案例此后 Windows 错误码 0，Intel 输出 1080p/60 Hz，用户确认物理显示恢复正常。这个结果支持在本案例保留该配置；没有证明所有花屏都由 PCI 地址造成。

## 7. 无线接收器 USB 直通

先找设备和物理端口：

```bash
lsusb
lsusb -t
for dev in /sys/bus/usb/devices/*; do
  if [ -f "$dev/idVendor" ] && [ -f "$dev/idProduct" ]; then
    printf '%s %s:%s\n' "${dev##*/}" "$(cat "$dev/idVendor")" "$(cat "$dev/idProduct")"
  fi
done
```

案例是 Logitech `046d:c534`，端口 `3-5`。关闭 VM 后：

```bash
python3 scripts/pve-n150.py usb --vmid 102 --usb-port 3-5
python3 scripts/pve-n150.py usb --vmid 102 --usb-port 3-5 --apply
python3 scripts/pve-n150.py start --vmid 102 --apply
```

配置为 `usb0: host=3-5`，跟随插口，换插口后需要更新。脚本限定本次验证过的接收器 ID；其他 USB 设备可按 PVE 的普通 USB 配置流程另行处理。

案例的 USB 控制器 `00:14.0` 与 `00:14.2` 同组，没有整体直通控制器。音频 `00:1f.3` 与 `00:1f.0/1f.4/1f.5` 在 group 12，也没有直通。不能把这两个控制器当作独立 group 设备照搬。

## 8. 内存、128 MiB 预留和最终验收

案例最终使用 **4 GiB 固定内存**；曾改为 6 GiB，但 16 GiB 主机上还有 8 GiB 服务 VM 和 1 GiB 路由 VM，宿主余量不足，于是改回 4 GiB并启动验证。

```bash
qm shutdown 102 --timeout 60
python3 scripts/pve-n150.py memory --vmid 102 --memory-mib 4096 --apply
python3 scripts/pve-n150.py start --vmid 102 --apply
```

启动脚本要求宿主 `MemAvailable` 至少达到客体内存加 256 MiB，这是最低预检余量，不是宿主负载稳定的保证。通常还应给 PVE 留更宽裕的实际内存。

PCI 直通的 DMA 映射使动态 Balloon 回收不适用。Balloon 设备可在最小内存等于最大内存时用于统计；本案例保持 `balloon: 0`，没有依赖内存超分。[Proxmox 官方开发说明](https://lists.proxmox.com/pipermail/pve-devel/2023-November/060055.html)

这里的 **128 MiB 是启动阶段 DSM 预留**。Intel 核显可以动态使用共享系统内存，Windows 显示的专用显存数字不能代表总可用显存；共享上限也不是提前占用。当前正常的 1080p 桌面没有显示需要增加这个预留。[Intel 显存说明](https://www.intel.com/content/www/us/en/support/articles/000020962/graphics.html)

在 Windows 管理员 PowerShell 运行仓库的 `scripts/verify-windows.ps1`，或直接检查：

```powershell
Get-CimInstance Win32_VideoController |
  Select-Object Name,Status,ConfigManagerErrorCode,DriverVersion,
                CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate
Get-PnpDevice -PresentOnly |
  Where-Object { $_.InstanceId -like '*VID_046D&PID_C534*' } |
  Select-Object Class,FriendlyName,Status
```

验收要同时确认：Intel GPU 错误码为 0、Intel 的当前分辨率正确、物理屏幕显示稳定、键鼠可以操作，再正常关闭并启动一次复验。虚拟 VGA 与 Intel 显卡同时存在是本案例的预期结果。

## 9. 失败与回滚

脚本每次变更输出 `BACKUP=/root/n150-pve-backups/VMID/...`。先正常关闭 Windows；只对本阶段的检查点回滚：

```bash
qm shutdown 102 --timeout 60
qm status 102
python3 scripts/pve-n150.py rollback --vmid 102 --backup /root/n150-pve-backups/102/YOUR_CHECKPOINT
python3 scripts/pve-n150.py rollback --vmid 102 --backup /root/n150-pve-backups/102/YOUR_CHECKPOINT --apply
```

回滚只恢复配置，VM 保持停止，不删除 ROM、不恢复磁盘。再次启动使用单独的 `start --apply`。若配置已被后续修改，脚本拒绝覆盖：先比较当前配置与检查点，保留后来改动，再手动处理。

一次测试失败后收集启动错误、`qm showcmd`、Windows 错误码、QMP 寄存器，再决定下一步。不要同时堆叠多个参数后把结果归因给其中某一个。
