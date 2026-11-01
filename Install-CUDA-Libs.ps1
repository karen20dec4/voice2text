# Downloads NVIDIA cuBLAS and cuDNN (CUDA 12, about 1.3 GB) into cuda\ beside the application.
param(
    [string]$CublasUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-win-cuda-12.4.0-x64.zip",
    [string]$CudnnUrl = "https://files.pythonhosted.org/packages/aa/38/f856579877f7c1c5066e61182e7de7bc27bf35a78c8d1b0fa592e6985bc4/nvidia_cudnn_cu12-9.27.0.42-py3-none-win_amd64.whl"
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Expand-Dlls($Url, $Pattern, $Target) {
    $archive = Join-Path $Target "download.tmp"
    curl.exe -L --fail --progress-bar -o $archive $Url
    if ($LASTEXITCODE -ne 0) { throw "Descărcare eșuată: $Url" }
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $entries = @($zip.Entries | Where-Object { $_.Name -match $Pattern })
        if ($entries.Count -eq 0) { throw "Arhiva nu conține $Pattern" }
        foreach ($entry in $entries) {
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $Target $entry.Name), $true)
        }
    } finally {
        $zip.Dispose()
        Remove-Item $archive -Force
    }
}

$target = Join-Path $PSScriptRoot "cuda"
New-Item -ItemType Directory -Force $target | Out-Null
Expand-Dlls $CublasUrl "^(cublas64_12|cublasLt64_12|cudart64_12)\.dll$" $target
Expand-Dlls $CudnnUrl "^cudnn.*64_9\.dll$" $target
Write-Host "Bibliotecile CUDA sunt în $target. Repornește Voice2Text."
