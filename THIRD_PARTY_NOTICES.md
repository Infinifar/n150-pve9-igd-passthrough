# Third-party source and firmware notices

The root MIT license does not replace the licenses of the following materials.

## Intel-published IgdAssignmentDxe patches

`source/Intel-IgdHeaders.patch` and `source/Intel-IgdAssignmentDxe.patch` are
archived from the Intel ECI 3.3 documentation. Original patch authors, signed-off
lines, copyright notices and license headers are preserved in the files.

The four extracted source files carry BSD license notices, including:

- Copyright (C) 2018, Red Hat, Inc.
- Copyright (c) 2016 - 2019, Intel Corporation. All rights reserved.

See the source headers and `licenses/EDK2-2018-License.txt` for the accompanying
historical EDK2 license. The N150 adaptation is a separately archived patch;
redistributed adapted source continues to preserve the original notices.

## EDK2 libraries in the archived option ROM

The archived ROM was linked with libraries from Tianocore EDK2 commit
`2970e5699ba6267f3384ffab20f96647578aebc8`. Its upstream license, including BSD
2-Clause and package-specific notices, is reproduced in
`licenses/EDK2-License.txt`. The ROM includes the Intel-published initialization
driver and its N150 adaptation. It contains no proprietary Intel GOP driver.

MIPI Sys-T and Brotli are fetched as pinned build dependencies. They are not
vendored in this repository; their upstream source trees retain their own
license files. The pinned source and dependency links are listed in docs/BUILD.md.

Original upstream locations:

- https://eci.intel.com/docs/3.3/components/kvm-hypervisor.html
- https://github.com/tianocore/edk2/tree/2970e5699ba6267f3384ffab20f96647578aebc8
- https://github.com/MIPI-Alliance/public-mipi-sys-t/tree/370b5944c046bab043dd8b133727b2135af7747a
- https://github.com/google/brotli/tree/e230f474b87134e8c6c85b630084c612057f253e
