#!/usr/bin/env bash
# Offline repacking only. No block devices, mounts, flash commands or paid APIs.
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
input=""
out="${repo}/out"
cache="${PANTHER_INPUT_DIR:-${repo}/downloads}"
while (($#)); do
  case "$1" in
    --input) input="$2"; shift 2 ;;
    --out) out="$2"; shift 2 ;;
    *) echo "Usage: $0 [--input freshly-built.img] [--out output-directory]" >&2; exit 2 ;;
  esac
done
mkdir -p "${cache}/loaders" "${out}"
manifest="${repo}/compat/inputs.json"
fetch() {
  local url="$1" sha="$2" size="$3" dest="$4"
  if [[ ! -f "${dest}" ]]; then
    curl --fail --location --retry 5 --connect-timeout 20 --max-time 1800 \
      "${url}" --output "${dest}.partial"
    printf '%s  %s\n' "${sha}" "${dest}.partial" | sha256sum --check -
    test "$(wc -c < "${dest}.partial")" -eq "${size}"
    mv -- "${dest}.partial" "${dest}"
  fi
  printf '%s  %s\n' "${sha}" "${dest}" | sha256sum --check -
  test "$(wc -c < "${dest}")" -eq "${size}"
}
while IFS=$'\t' read -r name url sha size; do
  fetch "${url}" "${sha}" "${size}" "${cache}/loaders/${name}"
done < <(jq -r '.loaders[] | [.name,.url,.sha256,.size] | @tsv' "${manifest}")

if [[ -z "${input}" ]]; then
  IFS=$'\t' read -r url sha size < <(jq -r '.base | [.url,.sha256,.size] | @tsv' "${manifest}")
  fetch "${url}" "${sha}" "${size}" "${cache}/vendor-base.img.xz"
  # Always decompress the checksum-verified archive; do not trust a stale raw cache.
  xz --decompress --stdout "${cache}/vendor-base.img.xz" > "${cache}/vendor-base.img.tmp"
  mv -- "${cache}/vendor-base.img.tmp" "${cache}/vendor-base.img"
  input="${cache}/vendor-base.img"
fi

name="Armbian_Panther-X2_trixie_BSP6.1.115_ophub-bootchain_candidate"
image="${out}/${name}.img"
for path in "${image}" "${image}.xz" "${image}.xz.sha256" "${out}/bootchain-validation.json"; do
  if [[ -e "${path}" || -L "${path}" ]]; then
    echo "Refusing existing output: ${path}" >&2
    exit 1
  fi
done
"${PYTHON:-python3}" "${repo}/scripts/graft_bootchain.py" \
  --image "${input}" --output "${image}" --loader-dir "${cache}/loaders" \
  > "${out}/bootchain-validation.json.tmp"
mv -- "${out}/bootchain-validation.json.tmp" "${out}/bootchain-validation.json"
xz --threads=2 -3 --keep "${image}"
(
  cd -- "${out}"
  sha256sum "${name}.img.xz" > "${name}.img.xz.sha256"
  sha256sum --check "${name}.img.xz.sha256"
)
rm -- "${image}"
cp -- "${manifest}" "${out}/inputs.json"
printf '\nOffline candidate complete. Hardware boot and NPU/VPU runtime are NOT tested.\n'
ls -lh "${out}"
