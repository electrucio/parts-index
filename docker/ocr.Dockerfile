# The OCR stage, and only that. It is the one part of this project that wants a GPU, and the one whose
# dependencies are heavy and CUDA-bound, so it is the one part that ships as an image — that is what makes
# it reproducible on another machine instead of rebuilt there by hand.
#
#   docker build -f docker/ocr.Dockerfile -t parts-index-ocr .
#   docker run --rm --gpus '"device=0"' \
#     -v "$PWD":/repo -v "$PWD/private_material":/repo/private_material \
#     parts-index-ocr schematics ocr --source audiocircuit --gpu 0 --shard 0/2
#
# Several shards run beside one another, one per GPU: they take disjoint documents, append to the map and
# stamp their own ledger rows. Nothing is read twice — the ledger decides, not the order they finish in.
# The CUDA of the base has to be one the host's driver runs: a 535 driver tops out at CUDA 12.2 and refuses
# the 12.6 build outright ("unsatisfied condition: cuda>=12.6"), so a machine like that builds with
#   docker build --build-arg PADDLE_TAG=3.2.2-gpu-cuda11.8-cudnn8.9 -f docker/ocr.Dockerfile -t parts-index-ocr .
ARG PADDLE_TAG=3.2.2-gpu-cuda12.6-cudnn9.5
FROM paddlepaddle/paddle:${PADDLE_TAG}

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /repo
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN python -m pip install --upgrade pip \
 && python -m pip install "paddleocr>=3.0" "pymupdf>=1.24" "pillow>=10" "pyyaml>=6" "requests>=2.31"

# The package is mounted, not copied: the image holds the dependencies, the repository holds the code, so
# a change to the code does not rebuild the image.
ENV PYTHONPATH=/repo/src
ENTRYPOINT ["python", "-m", "parts_index.cli"]
CMD ["schematics", "ocr", "--help"]
