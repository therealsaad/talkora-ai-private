import asyncio


# Parler and faster-whisper share a 6 GB GPU. A process-wide lock prevents their
# peak allocations from overlapping while both singleton models stay resident.
gpu_inference_lock = asyncio.Lock()
