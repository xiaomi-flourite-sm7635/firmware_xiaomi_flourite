# flourite stock firmware dumps

Complete raw partition dumps for reproducible extraction of the **unified**
POCO M8 Pro 5G / Redmi Note 15 Pro+ 5G vendor. These are extraction inputs,
not separate custom ROM builds and not flashable update packages.

| Source | Role |
| --- | --- |
| OS3.0.306.0.WPRMIXM | Global base, shared HALs and firmware |
| OS3.0.318.0.WPRCNXM | Chinese radio firmware, camera descriptors/tuning and TMS NFC/eSE |

Release assets contain every partition present in the corresponding original
full OTA payload, split into numbered archives below GitHub's per-file limit.
`sources.json` records the original ZIP and partition hashes. No userdata,
device-specific calibration dumps, tester logs or development tools are added.

## Extract

Download both sets of release parts, `sources.json` and `SHA256SUMS` into the same directory.
Verify **all** parts before extraction, then reconstruct each archive:

```sh
sha256sum -c SHA256SUMS
mkdir global china
cat global-306-raw.tar.zst.part* | zstd -d | tar -xf - -C global
cat china-318-raw.tar.zst.part* | zstd -d | tar -xf - -C china
```

In a LineageOS checkout with `tools/extract-utils` and its extract-tool
prebuilts, unpack the Chinese filesystem partitions first:

```sh
python3 tools/extract-utils/extract.py --keep-images -- /absolute/path/to/china
PYTHONPATH=tools/extract-utils python3 device/xiaomi/flourite/extract-files.py /absolute/path/to/global \
    --china-source /absolute/path/to/china \
    --global-modem /absolute/path/to/global/modem.img \
    --china-modem /absolute/path/to/china/modem.img
```

Use the matching device tree with `firmware_sources.py` and compatibility
patch 0006. Its `firmware-sources.json` selects and verifies only the required
CN additions and both regional modem images. Shared HALs remain sourced from
Global; do not overlay the entire Chinese dump on the Global dump. Android
mounts the matching modem image from vendor read-only, selected by hardware
SKU. Its firmware and MBN profiles update with the ROM, without flashing the
modem partitions. The resulting vendor supports **one ROM/OTA for all variants**.

The proprietary blobs remain copyrighted by their respective owners. The
dump does not grant additional rights or constitute official Xiaomi support.

## Reproduce the release

`package.py` accepts the two original full OTA ZIPs and the AOSP
`ota_extractor` executable. It extracts raw images without using a phone,
records SHA-256 hashes, and creates reproducible split archives. It refuses
to overwrite an existing output directory. Python 3, GNU tar and zstd are
required.

```sh
python3 package.py --global-ota /path/to/global.zip --china-ota /path/to/china.zip \
    --extractor /path/to/ota_extractor --output artifacts
```
