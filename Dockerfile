# bonsai2-run: llama-server from PrismML's llama.cpp fork + DFlash2 patches, CUDA sm_89 (L4) and sm_120 (RTX PRO 6000).
# Cloud Run GPUs ship NVIDIA driver 580 (CUDA 13.0), so a CUDA 12.8 image runs on both.
ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=24.04

FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS build
# PrismML-Eng/llama.cpp master at 2026-09-21; patches/ bring it to our llama.cpp-prism dflash2-port commit cbe495c59.
ARG PRISM_SHA=9a9394a895b96003ca842a6041cb28ac49a108f7
ARG CUDA_ARCHS="89;120"
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates \
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
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/bin/llama-server /app/llama-server
COPY entrypoint.sh /app/entrypoint.sh
ENV PORT=8080 CUDA_MODULE_LOADING=LAZY
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
