FROM gcc:16.2@sha256:07280eb2e744f1b7a2d8d4a3894c089ea07266c109758afc388a634bd098e4eb
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-venv pkg-config libssl-dev ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/cmake && \
    /opt/cmake/bin/pip install --no-cache-dir cmake==4.4.3
ENV PATH="/opt/cmake/bin:${PATH}" LD_LIBRARY_PATH=/usr/local/lib
ADD --checksum=sha256:23c8575c7d1ced07246cb9cf200c11325b72201fd4134a02414ca869fbdd8ed3 \
    https://github.com/confluentinc/librdkafka/archive/refs/tags/v2.15.1.tar.gz /tmp/librdkafka.tar.gz
RUN tar -xzf /tmp/librdkafka.tar.gz -C /tmp && \
    cmake -S /tmp/librdkafka-2.15.1 -B /tmp/librdkafka-build \
      -DCMAKE_BUILD_TYPE=Release -DRDKAFKA_BUILD_EXAMPLES=OFF -DRDKAFKA_BUILD_TESTS=OFF \
      -DWITH_SSL=ON -DWITH_CURL=OFF -DWITH_SASL=OFF && \
    cmake --build /tmp/librdkafka-build --parallel 4 && \
    cmake --install /tmp/librdkafka-build && \
    rm -rf /tmp/librdkafka* && ldconfig && \
    test "$(pkg-config --modversion rdkafka)" = 2.15.1
WORKDIR /workspace
COPY CMakeLists.txt CMakePresets.json ./
COPY cmake ./cmake
COPY simulator ./simulator
COPY kafka ./kafka
RUN test "$(g++ -dumpfullversion)" = 16.2.0 && \
    cmake --preset kafka -DCMAKE_BUILD_TYPE=Release && \
    cmake --build --preset kafka --parallel 4 && ctest --preset kafka --parallel 4
USER 10001:10001
ENTRYPOINT ["/workspace/build/kafka/simulator/device_simulator"]
CMD ["--output", "kafka", "--steps", "2"]
