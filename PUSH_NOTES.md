# Publication notes — 2026-10-12 (Asia/Shanghai)

Destination: public repository `Infinifar/n150-pve9-igd-passthrough`.

This publication contains a Chinese tutorial, the actual test sequence, reusable
scripts, pinned source patches and the tested initialization ROM. It preserves
the distinction between official QEMU packages and the custom N150 firmware.

The original hardware validation was performed on 2026-10-07. Publishing the
repository does not restart or reconfigure the running PVE host/VM. Script write
operations are tested in a simulated host; CI also checks a clean source build.

Private SSH material, host addresses, complete VM configs, MAC/UUID identifiers,
Windows device instance paths and raw host logs are excluded. The actual staged
file list, ROM hash, documentation links and tests are checked before publication.
