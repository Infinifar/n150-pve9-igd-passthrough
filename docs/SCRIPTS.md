# 脚本参考

Python 脚本仅使用标准库。在 PVE 以 root 执行，必须显式传入 `--vmid`。`--help` 可以在其他系统查看。

```bash
python3 scripts/pve-n150.py ACTION --vmid 102 [OPTIONS]
```

| ACTION | 内容 | 参数 |
| --- | --- | --- |
| inspect | 只读版本、配置、驱动、分组、可用内存、启动命令 | 无 |
| stage1 | 只设置最小 hostpci0；不会撤掉已有成功 ROM | `--apply` 才写入 |
| rom | 校验并安装实测 ROM，更新 hostpci0 | `--apply` 才写入 |
| root-pci | 用原生 `-set` 指定客体 00:02.0 | `--apply` 才写入 |
| memory | 修改固定内存；不改变 Balloon | `--memory-mib 4096`，`--apply` 才写入 |
| start | 检查内存并尝试启动一次 | `--apply` 才启动 |
| rollback | 恢复指定检查点的 before.conf | `--backup DIR`，`--apply` 才写入 |

`inspect` 是严格预检：若前提不成立，它会报具体拒绝原因，不保证输出后续所有项目。可先用教程中的单项命令排查。它的输出含使用者本机配置，发布前需要筛选。

配置操作要求 VM 已停止；脚本不自动关机、不强制停止、不安排宿主重启，不更改磁盘内容、启动器参数、VFIO 绑定或 QEMU 软件包。

## 拒绝覆盖的情况

预检要求 PVE 9.2、QEMU 11 包文件完整、现有 OVMF/EFI 磁盘、pc-q35-11.0、虚拟显示设备、指定 N150 GPU 由 VFIO 接管且独占 group。它拒绝 pending 配置、锁定 VM、模板、其他 VM 占用 GPU、额外 hostpci、自定义 args，以及未识别的 hostpci0 参数。

`memory` 要求当前 `balloon: 0`，避免把动态最小值与固定内存混在一起。只改内存字段。`start` 检查 `MemAvailable >= 配置内存 + 256 MiB`；仍应按主机业务负载留出充足余量。

`rom` 固定归档文件 SHA256，已有目标 ROM 与归档不同则拒绝覆盖。`root-pci` 不会拼接到未知 QEMU args；它先检查生成命令中的根总线 slot 2 是否已经被占用。

执行期间不要通过其他终端或 PVE UI 同时修改目标 VM；检查与写入之间不应插入其他管理操作。

## 检查点

默认在 `/root/n150-pve-backups/VMID/时间-动作-随机后缀/` 保存：

```text
before.conf / after.conf
metadata.json（VMID、动作、配置 SHA256）
showcmd.before.txt / showcmd.after.txt
start.log（启动动作）
showcmd.failed.txt（启动失败时）
```

目录权限 0700。回滚验证目标 VMID、before.conf 哈希、当前配置是否仍等于本检查点的 after 哈希。只恢复紧邻当前状态的检查点；分阶段撤回时从最后一次配置修改向前逐次恢复。不会一口气覆盖中间新增的配置。

回滚会再备份当前配置，保留 ROM 文件，VM 不会自动启动。启动失败时保存错误和启动命令，不自动添加兼容参数。

## 寄存器与 Windows 检查

```bash
python3 scripts/inspect-igd-qmp.py --vmid 102
python3 scripts/inspect-igd-qmp.py --vmid 102 --output /root/private-igd-check
```

QMP 脚本要求 VM 已运行、采用 q35 并存在 `hostpci0` 的 `8086:46d4` GPU。它使用 `query-pci` 和只读内存查询，不执行 register/memory 写入。`--output` 保存客体 PCI 信息，分享前需要检查内容。

把 `scripts/verify-windows.ps1` 放入 Windows 后，以管理员 PowerShell 执行。输出不包含设备实例路径，查看 GPU 错误码、驱动版本、分辨率与 Secure Boot。结果仍需结合物理屏幕的实际显示情况。
