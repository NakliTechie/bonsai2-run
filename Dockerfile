# bonsai2-run: llama-server from PrismML's llama.cpp fork + DFlash2 patches, CUDA sm_89 (L4) and sm_120 (RTX PRO 6000).
# Cloud Run GPUs ship NVIDIA driver 580 (CUDA 13.0), so a CUDA 12.8 image runs on both.
ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=24.04

FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS build
# PrismML-Eng/llama.cpp prism head 2026-09-24 (has the Hadamard borrow fix, PrismML #210); patches/ adds DFlash2 (ggml-org #27816).
ARG PRISM_SHA=ee8ad0ef6b03b34b8709ea9440a4b3927e8a6524
ARG CUDA_ARCHS="89;120"
# retried: Ubuntu mirrors 404 mid-sync now and then (seen 2026-09-24 on libexpat1)
RUN ok=; for i in 1 2 3; do apt-get update && apt-get install -y --no-install-recommends --fix-missing git cmake build-essential ca-certificates && ok=1 && break; sleep 20; done; [ -n "$ok" ] \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git init -q . && git remote add origin https://github.com/PrismML-Eng/llama.cpp.git \
    && git fetch -q --depth 1 origin ${PRISM_SHA} && git checkout -q FETCH_HEAD
COPY patches/ /patches/
RUN git -c user.name=build -c user.email=build@localhost am -q /patches/*.patch
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DGGML_NATIVE=OFF \
        -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHS}" -DBUILD_SHARED_LIBS=OFF \
        -DLLAMA_BUILD_UI=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
    && cmake --build build --target llama-server -j"$(nproc)" \
    && strip build/bin/llama-server

FROM docker.io/nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION}
RUN ok=; for i in 1 2 3; do apt-get update && apt-get install -y --no-install-recommends --fix-missing libgomp1 curl ca-certificates && ok=1 && break; sleep 20; done; [ -n "$ok" ] \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/bin/llama-server /app/llama-server
COPY entrypoint.sh /app/entrypoint.sh
ENV PORT=8080 CUDA_MODULE_LOADING=LAZY
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
