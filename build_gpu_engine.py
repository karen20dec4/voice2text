"""Build gpu/voice2text_whisper.dll: whisper.cpp with Vulkan, for AMD, NVIDIA and Intel cards."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

WHISPER_TAG = "v1.9.5"
WHISPER_REPOSITORY = "https://github.com/ggml-org/whisper.cpp"
# conda-forge packages replace the Vulkan SDK, whose installer needs elevation.
VULKAN_PACKAGES = ("shaderc", "glslang", "spirv-tools", "spirv-headers",
                   "libvulkan-headers", "libvulkan-loader")


def fetch_vulkan_tools(target):
    import zstandard
    for name in VULKAN_PACKAGES:
        with urllib.request.urlopen(f"https://api.anaconda.org/package/conda-forge/{name}") as reply:
            files = json.load(reply)["files"]
        files = [f for f in files if f["attrs"]["subdir"] in ("win-64", "noarch")
                 and f["basename"].endswith(".conda")]
        newest = max(files, key=lambda f: f["attrs"].get("timestamp", 0))
        with urllib.request.urlopen(f"https://conda.anaconda.org/conda-forge/{newest['basename']}") as reply:
            package = zipfile.ZipFile(io.BytesIO(reply.read()))
        inner = next(n for n in package.namelist() if n.startswith("pkg-"))
        stream = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(package.read(inner)))
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            archive.extractall(target, filter="data")


def main():
    root = Path(__file__).resolve().parent
    stage = root / ".build"
    tools = stage / "build-tools"
    source = stage / "whisper.cpp"
    vulkan = stage / "vk-tools" / "Library"

    if not tools.exists():
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--target", str(tools),
                        "cmake", "ninja", "zstandard"], check=True)
    sys.path.insert(0, str(tools))
    if not source.exists():
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", WHISPER_TAG,
                        WHISPER_REPOSITORY, str(source)], check=True)
    if not vulkan.exists():
        fetch_vulkan_tools(vulkan.parent)

    cmake = tools / "cmake" / "data" / "bin" / "cmake.exe"
    ninja = tools / "bin" / "ninja.exe"
    build = stage / "gpu-engine"
    subprocess.run([str(cmake), "-S", str(root / "native"), "-B", str(build), "-G", "Ninja",
                    f"-DCMAKE_MAKE_PROGRAM={ninja}", "-DCMAKE_BUILD_TYPE=Release",
                    "-DCMAKE_C_COMPILER=cl", "-DCMAKE_CXX_COMPILER=cl",
                    f"-DWHISPER_SOURCE={source}", f"-DCMAKE_PREFIX_PATH={vulkan}",
                    f"-DVulkan_INCLUDE_DIR={vulkan / 'include'}",
                    f"-DVulkan_LIBRARY={vulkan / 'lib' / 'vulkan-1.lib'}",
                    f"-DVulkan_GLSLC_EXECUTABLE={vulkan / 'bin' / 'glslc.exe'}"], check=True)
    subprocess.run([str(cmake), "--build", str(build), "--target", "voice2text_whisper"], check=True)

    target = root / "gpu"
    target.mkdir(exist_ok=True)
    shutil.copy2(build / "voice2text_whisper.dll", target / "voice2text_whisper.dll")
    print(f"Motor GPU pregătit: {target / 'voice2text_whisper.dll'}")


if __name__ == "__main__":
    main()
