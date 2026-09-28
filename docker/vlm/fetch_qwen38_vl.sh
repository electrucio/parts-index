#!/bin/sh
# Qwen3.8-27B (unsloth UD-Q4_K_M, the file machin serves) + its vision projector, each checked against
# the sha256 pinned here (a changed file on Hugging Face is refused, not used).
#   sh docker/vlm/fetch_qwen38_vl.sh MODEL_DIR
set -eu
DEST=${1:?give the model folder}
mkdir -p "$DEST" && cd "$DEST"
get() {  # file sha256
  if [ -f "$1" ] && echo "$2  $1" | sha256sum -c - >/dev/null 2>&1; then echo "have $1"; return; fi
  curl -fL --retry 5 -C - -o "$1.part" "https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/$1"
  mv "$1.part" "$1"
  echo "$2  $1" | sha256sum -c -
}
get mmproj-F16.gguf cbb841a9ee0636b2ec172f5bb8df2ea8dfeb01e90fe7c6126581d662a0b4e43e
get Qwen3.8-27B-UD-Q4_K_M.gguf 322e194ff79741c7baa497c240f677f54b201b0efab44ca8e50f122b39123482
sha256sum mmproj-F16.gguf Qwen3.8-27B-UD-Q4_K_M.gguf > SHA256SUMS
echo done
