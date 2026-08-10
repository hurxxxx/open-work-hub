FROM opensearchproject/opensearch:3.3.2@sha256:798cf28e226a32f5c928dd1ed9478dd3a33d2212176aad3679020088ad3afa1a

# Analyzer plugins must exactly match the OpenSearch server version. Building the
# image makes that contract reproducible instead of installing into a live node.
RUN /usr/share/opensearch/bin/opensearch-plugin install --batch analysis-nori
