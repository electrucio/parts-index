# docker/vlm — a vision-language model on one GPU, for the data-sheet experiments

llama.cpp's `llama-server` built for an RTX 4090 on a host whose NVIDIA driver (535) stops at CUDA 12.2,
serving **Qwen3.8-27B** — a natively multimodal model — with its vision projector, through the
OpenAI-compatible `/v1/chat/completions` API. `docker/datasheets/` is what uses it.

```sh
make vlm-image                 # build (≈4 min): CUDA 12.2 base images by digest, llama.cpp at a fixed commit
make vlm-models                # fetch the weights (16.5 GB + 0.9 GB) into $VLM_MODELS, checked by sha256
make vlm-serve GPU=1           # container vlm-qwen on 127.0.0.1:8090; ready in seconds once cached
make vlm-stop
```

| input | pinned by |
|---|---|
| `nvidia/cuda:12.2.2-devel/runtime-ubuntu22.04` | digest (`docker/vlm/Dockerfile`) |
| llama.cpp | commit `4ceb171` — the one machin's text server runs, so both read the same GGUF the same way |
| `Qwen3.8-27B-UD-Q4_K_M.gguf` (unsloth) | sha256 `322e194f…`, checked on download (`fetch_qwen38_vl.sh`) |
| `mmproj-F16.gguf` (unsloth, vision projector) | sha256 `cbb841a9…` |

The weights are not in the image; they are mounted read-only from `$VLM_MODELS`, a folder outside the
repository. The same Q4_K_M file is what machin serves as a text
model — without the projector — for the summarise pass; with it, the model reads images.

**What it takes on lola's GPU 1:** 19.4 GB with `-c 32768 -np 2` (two requests at once, 16 k tokens each).
A data-sheet page at 150 dpi is ≈ 2,000 image tokens; the model writes ≈ 48 tokens/s; a page of
characteristics comes back in 20–60 s. Thinking is switched off per request
(`chat_template_kwargs: {enable_thinking: false}`): the task is transcription, not reasoning.

**Why llama.cpp and not vLLM:** vLLM's images need a newer CUDA than lola's 535 driver runs. The
build links against the driver's `libcuda` lazily (`-Wl,--allow-shlib-undefined`, as upstream's own
Dockerfile does), because the driver only exists at run time, not in a build container.

**Sharing the GPU:** GPU 1 of lola is the experiments GPU; GPU 0 belongs to other people's work. The
container holds its 19 GB until `make vlm-stop`.
