import time
import tempfile
from pathlib import Path
from services.download_service_async import download_file_optimized

# URLs de teste confiáveis (Hetzner)
RANGE_URL = "https://nbg1-speed.hetzner.com/100MB.bin"
NO_RANGE_URL = "https://nbg1-speed.hetzner.com/100MB.bin"
MIRRORS = [
    "https://nbg1-speed.hetzner.com/100MB.bin",
    "https://hel1-speed.hetzner.com/100MB.bin",
]

def benchmark_download(url, mirrors=None, profile="aggressive"):
    temp_dir = Path(tempfile.mkdtemp())
    start = time.time()
    path = None
    try:
        path = asyncio.run(download_file_optimized(
            url, temp_dir, mirrors=mirrors, profile=profile, verify_ssl=False
        ))
    except Exception as e:
        print(f"Erro: {e}")
        return None
    elapsed = time.time() - start
    size = path.stat().st_size if path and path.exists() else 0
    throughput = size / elapsed if elapsed > 0 else 0
    print(f"URL: {url}\nProfile: {profile}\nTempo: {elapsed:.2f}s\nTamanho: {size/1024/1024:.2f} MiB\nThroughput: {throughput/1024/1024:.2f} MiB/s\n")
    return elapsed, throughput

if __name__ == "__main__":
    import asyncio
    print("Benchmark: Multipart (aggressive)")
    benchmark_download(RANGE_URL, profile="aggressive")
    print("Benchmark: Single-stream (safe)")
    benchmark_download(NO_RANGE_URL, profile="safe")
    print("Benchmark: Mirror racing (aggressive)")
    benchmark_download(MIRRORS[0], mirrors=MIRRORS, profile="aggressive")
