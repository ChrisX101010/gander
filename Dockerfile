FROM ubuntu:24.04 AS build

ARG GOOSE_COMMIT=335fddc13dc74666398ffe160ec8a8f2958329d0

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y \
       build-essential ca-certificates cmake git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/aardappel/goose.git /goose \
    && git -C /goose checkout "${GOOSE_COMMIT}" \
    && cmake -S /goose -B /goose/build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /goose/build --config Release --parallel 2

WORKDIR /src
COPY src/windowed.goose src/windowed.goose

RUN mkdir -p /out \
    && /goose/build/goose build --standalone -o /out/gander src/windowed.goose \
    && /out/gander --version

FROM ubuntu:24.04
LABEL org.opencontainers.image.source="https://github.com/ChrisX101010/gander"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.description="Bounded-memory deterministic event/state reducer written in Goose"
COPY --from=build /out/gander /usr/local/bin/gander
ENTRYPOINT ["/usr/local/bin/gander"]
