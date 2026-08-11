FROM alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce AS fetch

ARG BENTO_VERSION=1.0.17
ARG BENTO_SOURCE_REVISION=efc0fab48ed1a9531bb1ae2a652a091832f64254
ARG BENTO_ARTIFACT_SHA256=06026f088399a7422696ef122f424f09d4735fd128ae398392af31ce50ebdf9b
ARG BENTO_LICENSE_SHA256=98f7c83ee9c15064fef0198e2ec3228fa57628e5812583fd8cc6c98a42d5ad02
ARG BENTO_NOTICES_SHA256=f3838634253d4d4be866871e907b84f80401bba4c030e06cdefa95c8e608000e

RUN apk add --no-cache ca-certificates curl

WORKDIR /opt/bento

RUN curl --fail --location --retry 3 \
      --output index.html \
      "https://github.com/nyblnet/bento/releases/download/v${BENTO_VERSION}/Bento_Slides.bento.html" \
    && printf '%s  %s\n' "${BENTO_ARTIFACT_SHA256}" index.html | sha256sum -c \
    && curl --fail --location --retry 3 \
      --output LICENSE \
      "https://raw.githubusercontent.com/nyblnet/bento/${BENTO_SOURCE_REVISION}/LICENSE" \
    && printf '%s  %s\n' "${BENTO_LICENSE_SHA256}" LICENSE | sha256sum -c \
    && curl --fail --location --retry 3 \
      --output THIRD_PARTY_NOTICES.md \
      "https://raw.githubusercontent.com/nyblnet/bento/${BENTO_SOURCE_REVISION}/THIRD_PARTY_NOTICES.md" \
    && printf '%s  %s\n' "${BENTO_NOTICES_SHA256}" THIRD_PARTY_NOTICES.md | sha256sum -c \
    && test "$(grep -o '</body>' index.html | wc -l)" -eq 1 \
    && sed -i 's#</body>#<script src="/open-work-hub-bridge.js"></script></body>#' index.html \
    && grep -q 'src="/open-work-hub-bridge.js"' index.html

FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10

COPY ops/bento/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=fetch /opt/bento/index.html /usr/share/nginx/html/index.html
COPY ops/bento/open-work-hub-bridge.js /usr/share/nginx/html/open-work-hub-bridge.js
COPY --from=fetch /opt/bento/LICENSE /usr/share/nginx/html/licenses/LICENSE
COPY --from=fetch /opt/bento/THIRD_PARTY_NOTICES.md /usr/share/nginx/html/licenses/THIRD_PARTY_NOTICES.md

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
