#!/usr/bin/env python3
"""Download the exact published benchmark, without editing its source or data."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("RINHA_BENCHMARK_CACHE", ROOT / ".local" / "benchmark"))
LOCK = json.loads((ROOT / "benchmark" / "official-source.json").read_text())


def digest(path, algorithm="sha256"):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def download(url, path, expected):
    if path.exists() and digest(path) == expected:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Baixando {url}", file=sys.stderr)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                shutil.copyfileobj(response, stream)
            stream.flush()
            if digest(temporary) != expected:
                raise RuntimeError(f"SHA256 divergente: {url}; arquivo rejeitado")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def extract(archive, destination, expected_directory):
    marker = destination / ".verified-archive-sha256"
    checksum = digest(archive)
    if marker.exists() and marker.read_text().strip() == checksum and (destination / expected_directory).is_dir():
        return
    destination.mkdir(parents=True, exist_ok=True)
    # Extract into a new directory: an interrupted extraction may leave read-only files.
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        staging = Path(temporary)
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as bundle:
                for item in bundle.infolist():
                    if not (staging / item.filename).resolve().is_relative_to(staging.resolve()):
                        raise RuntimeError("Caminho inválido no arquivo ZIP")
                bundle.extractall(staging)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(staging, filter="data")
        target = destination / expected_directory
        if target.exists():
            shutil.rmtree(target)
        (staging / expected_directory).replace(target)
    marker.write_text(checksum + "\n")


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    official = CACHE / "official" / LOCK["commit"]
    raw = "https://raw.githubusercontent.com/zanfranceschi/rinha-de-backend-2023-q3"
    for relative, checksum in LOCK["files"].items():
        download(f"{raw}/{LOCK['commit']}/{relative}", official / relative, checksum)

    gatling = LOCK["gatling"]
    archive = CACHE / "gatling" / "bundle.zip"
    download(gatling["url"], archive, gatling["sha256"])
    if digest(archive, "sha1") != gatling["publisher_sha1"]:
        raise RuntimeError("Checksum SHA1 publicado pelo Maven diverge do bundle")
    gatling_directory = f"gatling-charts-highcharts-bundle-{gatling['version']}"
    extract(archive, archive.parent, gatling_directory)
    gatling_home = archive.parent / gatling_directory

    supplied_java = os.environ.get("BENCHMARK_JAVA_HOME")
    if supplied_java:
        java_home = Path(supplied_java).resolve()
    else:
        if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
            raise RuntimeError("Nesta plataforma, informe BENCHMARK_JAVA_HOME apontando para Java 17")
        java = LOCK["java"]
        archive = CACHE / "java" / "jre.tar.gz"
        download(java["url"], archive, java["sha256"])
        extract(archive, archive.parent, java["directory"])
        java_home = archive.parent / java["directory"]
    version = subprocess.run([str(java_home / "bin/java"), "-version"], capture_output=True, text=True, check=True)
    if 'version "17.' not in version.stderr:
        raise RuntimeError("Gatling 3.9.5 precisa de Java 17; Scala 2.13.10 falha em Java 21")
    output = {
        "cache": str(CACHE),
        "gatling_home": str(gatling_home),
        "java_home": str(java_home),
        "simulations": str(official / "stress-test/user-files/simulations"),
        "resources": str(official / "stress-test/user-files/resources"),
        "java_version": version.stderr.strip(),
        "source": LOCK,
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
