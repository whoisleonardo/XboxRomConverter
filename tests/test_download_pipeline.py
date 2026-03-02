import asyncio
import tempfile
import os
from pathlib import Path
import pytest
from services.download_service_async import download_file_optimized

# URLs de teste (substitua por URLs reais de arquivos grandes e pequenos, com e sem suporte a range)
RANGE_URL = os.environ.get("TEST_RANGE_URL", "https://speed.hetzner.de/100MB.bin")
NO_RANGE_URL = os.environ.get("TEST_NO_RANGE_URL", "https://nbg1-speed.hetzner.com/100MB.bin")
MIRRORS = [
    os.environ.get("TEST_MIRROR1", "https://speed.hetzner.de/100MB.bin"),
    os.environ.get("TEST_MIRROR2", "https://speedtest.tele2.net/100MB.zip"),
]

@pytest.mark.asyncio
async def test_download_multipart_resume():
    temp_dir = Path(tempfile.mkdtemp())
    # Download inicial
    path = await download_file_optimized(RANGE_URL, temp_dir, profile="aggressive", verify_ssl=False)
    assert path.exists() and path.stat().st_size > 0
    # Simular interrupção e resume
    os.remove(path)
    # Estado deve persistir
    path2 = await download_file_optimized(RANGE_URL, temp_dir, profile="aggressive", resume=True, verify_ssl=False)
    assert path2.exists() and path2.stat().st_size > 0

@pytest.mark.asyncio
async def test_download_single_stream():
    temp_dir = Path(tempfile.mkdtemp())
    path = await download_file_optimized(NO_RANGE_URL, temp_dir, profile="safe", verify_ssl=False)
    assert path.exists() and path.stat().st_size > 0

@pytest.mark.asyncio
async def test_mirror_racing():
    temp_dir = Path(tempfile.mkdtemp())
    path = await download_file_optimized(MIRRORS[0], temp_dir, mirrors=MIRRORS, profile="aggressive", verify_ssl=False)
    assert path.exists() and path.stat().st_size > 0
