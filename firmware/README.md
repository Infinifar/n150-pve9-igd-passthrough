# 实测初始化 ROM

`intel-igd-init-gen12-46d4.rom` 是 2026-10-07 实际构建并安装的产物。

- Vendor / Device：`8086:46d4`。
- 内容：Intel 发布的 IgdAssignmentDxe，加本仓库 `source/intel-n150-gen12.patch`。
- 工具链：EDK2 `2970e5699ba6267f3384ffab20f96647578aebc8`，X64 / DEBUG / GCC，EDK2 EfiRom 封装。
- 作用：建立 OpRegion 与 DSM，仅针对 N150 适配 Gen11+ BDSM 寄存器。
- 不包含 Intel 专有 GOP；不是从主板完整 BIOS 导出的 ROM。
- 安装路径：`/usr/share/kvm/intel-igd-init-gen12-46d4.rom`，由 `rom --apply` 安装。

在仓库根目录执行 `sha256sum -c firmware/SHA256SUMS` 核对。来源和许可见 [构建说明](../docs/BUILD.md)与[第三方声明](../THIRD_PARTY_NOTICES.md)。重新编译得到的文件可能因工具链和时间戳产生不同哈希，本仓库脚本固定使用这个实测产物，不接受替换后仍沿用原哈希。
