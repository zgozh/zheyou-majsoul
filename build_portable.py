"""Build the offline Windows x64 distribution from the prepared vendor inputs."""

from hashlib import file_digest
from importlib.metadata import distribution
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
NAME = "zheyou-majsoul-windows-x64"
PACKAGE_ROOT = ROOT / "dist" / NAME
PYTHON_MODULES = ("torch", "numpy", "typing_extensions", "filelock", "setuptools", "sympy",
                  "networkx", "jinja2", "markupsafe", "fsspec", "mpmath", "packaging")


def digest(path, algorithm="sha256"):
    with path.open("rb") as source:
        return file_digest(source, algorithm).hexdigest()


def copy_packages(target):
    for name in PYTHON_MODULES:
        package = distribution(name)
        for entry in package.files or ():
            if ".." in entry.parts or "__pycache__" in entry.parts or entry.suffix in (".lib", ".pdb", ".pyc"):
                continue
            source = Path(package.locate_file(entry))
            if source.is_file():
                path = target / entry
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, path)


def install_runtimes(runtime):
    python = runtime / "python"
    with ZipFile(VENDOR / "python-embed.zip") as archive:
        archive.extractall(python)
    (python / "python312._pth").write_text("python312.zip\n.\nsite-packages\n", encoding="ascii")
    copy_packages(python / "site-packages")

    java_metadata = json.loads((VENDOR / "java-release.json").read_text(encoding="utf-8"))
    if "sha256:" + digest(VENDOR / "temurin.zip") != java_metadata["digest"]:
        raise ValueError("Temurin ZIP checksum mismatch")
    with ZipFile(VENDOR / "temurin.zip") as archive:
        archive.extractall(runtime)
        directory = archive.namelist()[0].split("/")[0]
    (runtime / directory).rename(runtime / "java")

    djl = Path(os.environ.get("DJL_CACHE_DIR", Path.home() / ".djl.ai")) / "pytorch" / "2.11.0-cpu-win-x86_64"
    destination = runtime / "djl" / "pytorch" / djl.name
    destination.mkdir(parents=True)
    libraries = list(djl.glob("*.dll"))
    if not any(path.name.endswith("-djl_torch.dll") for path in libraries):
        raise ValueError("Start Epsilon once on the build machine to prepare its DJL CPU cache")
    for library in libraries:
        shutil.copy2(library, destination / library.name)
    (runtime / "VERSIONS.json").write_text(json.dumps({"python": "3.12.10", "java": java_metadata,
        "djl": djl.name, "python_packages": {name: distribution(name).version for name in PYTHON_MODULES}}, indent=2), encoding="utf-8")


def main():
    if PACKAGE_ROOT.exists():
        raise SystemExit(f"Move the previous staging folder before rebuilding: {PACKAGE_ROOT}")
    if digest(VENDOR / "python-embed.zip", "md5") != "fe8ef205f2e9c3ba44d0cf9954e1abd3":
        raise ValueError("Python embed ZIP checksum mismatch")
    subprocess.run([sys.executable, str(ROOT / "local_models/build_ui.py")], cwd=ROOT, check=True)
    app = PACKAGE_ROOT / "app"
    app.mkdir(parents=True)
    shutil.copy2(ROOT / "ZheyouClient.exe", app)
    shutil.copytree(ROOT / "defaults", app / "defaults")
    shutil.copytree(ROOT / "models", app / "models", ignore=shutil.ignore_patterns("__pycache__"))
    local = app / "local_models"
    local.mkdir()
    for name in ("server.py", "epsilon_worker.py", "EpsilonMjai.java"):
        shutil.copy2(ROOT / "local_models" / name, local)
    shutil.copytree(ROOT / "local_models/deps", local / "deps", ignore=shutil.ignore_patterns("__pycache__"))
    classes = local / "epsilon-classes"
    classes.mkdir()
    subprocess.run(["javac", "-encoding", "UTF-8", "-cp",
                    str(next((app / "models/epsilon-3p").glob("*.jar"))), "-d", str(classes),
                    str(local / "EpsilonMjai.java")], check=True)
    install_runtimes(app / "runtime")

    for name in ("README.md", "LICENSE.txt", "NOTICE", "THIRD_PARTY_LICENSES.md", "MODIFICATIONS.md"):
        shutil.copy2(ROOT / name, PACKAGE_ROOT)
    csc = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    subprocess.run([str(csc), "/nologo", "/target:winexe", "/platform:x64", "/reference:System.Windows.Forms.dll",
                    f"/out:{PACKAGE_ROOT / 'Zheyou.exe'}", str(ROOT / "local_models/Launcher.cs")], check=True)

    output = PACKAGE_ROOT.with_suffix(".zip")
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=3) as archive:
        for path in sorted(PACKAGE_ROOT.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.write(path, path.relative_to(PACKAGE_ROOT.parent))
    print(f"{output.name}  {output.stat().st_size:,} bytes  SHA256 {digest(output)}", flush=True)


if __name__ == "__main__":
    main()
