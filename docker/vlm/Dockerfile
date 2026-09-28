# syntax=docker/dockerfile:1.7
# llama.cpp's server, built for an RTX 4090 on a host whose driver stops at CUDA 12.2 (lola), to serve a
# vision-language model for the datasheet-table experiments. See docker/vlm/README.md.
#
#   make vlm-image
#   make vlm-serve GPU=1          # Qwen3.8-27B + its vision projector on port 8090
#
# Pinned: the CUDA base images by digest, llama.cpp by commit (the one machin's text server runs). The
# weights are not in the image: they are mounted from the model folder and checked by sha256 there.
ARG CUDA_DEVEL=nvidia/cuda:12.2.2-devel-ubuntu22.04@sha256:ae8a022c02aec945c4f8c52f65deaf535de7abb58e840350d19391ec683f4980
ARG CUDA_RUNTIME=nvidia/cuda:12.2.2-runtime-ubuntu22.04@sha256:94c1577b2cd9dd6c0312dc04dff9cb2fdce2b268018abc3d7c2dbcacf1155000

FROM ${CUDA_DEVEL} AS build
ARG LLAMA_COMMIT=4ceb1719101f32637b841206c172f3f058ffc182
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/ggml-org/llama.cpp /src && cd /src && git checkout ${LLAMA_COMMIT}
# libcuda (the driver) only exists at run time; the link leaves its symbols for the loader, as upstream does.
RUN cd /src && cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DGGML_NATIVE=OFF \
      -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-shlib-undefined \
 && cmake --build build -j"$(nproc)" --target llama-server llama-mtmd-cli \
 && mkdir -p /out && cp build/bin/llama-server build/bin/llama-mtmd-cli /out/ \
 && find build -name '*.so*' -exec cp -P {} /out/ \;

FROM ${CUDA_RUNTIME}
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/*
COPY --from=build /out /opt/llama
ENV LD_LIBRARY_PATH=/opt/llama PATH=/opt/llama:$PATH
ENTRYPOINT ["llama-server"]
