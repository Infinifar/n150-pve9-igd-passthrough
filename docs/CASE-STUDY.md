# 实际测试记录：2026-10-07

这里只公开经过筛选的结果。VMID 102 和端口 3-5 是案例参数；主机地址、连接凭据、完整配置和设备实例路径没有发布。

## 分阶段结果

| 阶段 | 显示相关变更 | 观察 |
| --- | --- | --- |
| Stage 1 | 官方 QEMU 11、OVMF、q35，仅 `hostpci0: 0000:00:02.0,pcie=1` | VM 启动，Windows Code 43；ASLS=0、BDSM=0 |
| 原始 Intel 初始化驱动 | 新增由 Intel 发布源码构建的基础 ROM | ASLS 有效，BDSM 仍为 0；Code 43 |
| N150 适配 ROM | 只替换 ROM 的 BDSM/设备匹配实现 | ASLS、BDSM 有效；Code 0；用户曾报告物理花屏/闪屏 |
| 客体 PCI 地址 | 同一 ROM，增加原生 `-set` 将 GPU 从 01:00.0 放到 00:02.0 | Code 0；用户确认显示正常 |
| 内存回调 | 6 GiB 改回 4 GiB 后启动 | Intel Code 0、1080p；接收器、键盘和鼠标 OK |

USB 接收器作为独立功能变更加入，不作为 Code 43 的修复因素。整个过程中没有更换 Windows Intel 驱动 `32.0.101.7088`，Secure Boot 仍开启。

## 最终读取到的运行状态

```text
Guest GPU BDF:       00:02.0
VID/DID:             0x46d48086
GGC:                 0x000004c1
DSM size:            128 MiB（沿用宿主值）
ASLS:                0x77fd5000
BDSM, Gen11+ 0xC0:   0x000000006ff00000
OpRegion signature:  IntelGraphicsMem
Windows GPU error:   0
Resolution / refresh:1920 x 1080 / 60 Hz
Secure Boot:         true
```

地址是当次客体内存分配结果，不能把这些十六进制地址写死到其他客体。诊断脚本应读取每次运行的真实值。

DXDiag 曾报告 Intel WDDM 2.7、DDI 12、No Problem。这是设备状态检查，不是 GPU 性能或游戏兼容性测试。

## IOMMU 与 USB

| 设备 | 案例分组 | 处理 |
| --- | --- | --- |
| 00:02.0 GPU | group 0，唯一设备 | PCIe 直通 |
| 00:1f.3 音频 | group 12，与 1f.0/1f.4/1f.5 同组 | 未直通 |
| 00:14.0 USB 控制器 | group 4，与 00:14.2 同组 | 未整体直通 |
| Logitech 046d:c534 | USB 端口 3-5 | `usb0: host=3-5`，键鼠 OK |

## 保留的边界

官方 QEMU 的包文件完整性检查未发现改变。外置 ROM 与 PCI 地址覆盖是最终方案的新增内容。

宿主物理 ROM 头读取曾有 `expecting 0xaa55, got 0x9fa2` 警告；外置 ROM 的 EFI/PCIR 结构另行检查，Windows 正常运行。不能把所有相似警告一概忽略，应结合实际启动与驱动状态。

初次适配 ROM 测试中出现过较长等待，最终客体自行启动。没有通过强制断电结束该轮测试。

物理显示恢复的结论来自 Windows 状态与用户实际观察共同确认。没有执行宿主重启、长期压力测试或其他设备 ID 测试；升级 PVE、QEMU、OVMF 或 Windows 驱动后应重新验收。
