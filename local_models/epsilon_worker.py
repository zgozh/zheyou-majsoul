# SPDX-License-Identifier: GPL-3.0-only
"""Run the Epsilon JVM in a separate Python process on Windows."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def main():
    directory = Path(__file__).resolve().parent
    sys.path.insert(0, str(directory / "deps"))
    import jpype

    jar = Path(sys.argv[1]).resolve()
    runtime = directory.parent / "runtime" / "java"
    classes = directory / "epsilon-classes"
    if runtime.is_dir() and classes.is_dir():
        with os.add_dll_directory(str(runtime / "bin")):
            jpype.startJVM("-Dai.djl.pytorch.num_threads=2", jvmpath=str(runtime / "bin/server/jvm.dll"),
                           classpath=[str(jar), str(classes)])
            try:
                jpype.JClass("EpsilonMjai").main([str(jar.parent)])
            finally:
                jpype.shutdownJVM()
        return

    compiler = shutil.which("javac")
    if not compiler:
        raise RuntimeError("Epsilon needs JDK 21 or newer on PATH")
    jvm = Path(compiler).resolve().parent / "server" / "jvm.dll"
    with TemporaryDirectory(prefix="zheyou-epsilon-") as classes:
        subprocess.run([compiler, "-encoding", "UTF-8", "-cp", str(jar), "-d", classes,
                        str(directory / "EpsilonMjai.java")], check=True, stdout=sys.stderr,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        # On this Windows installation c10.dll fails to initialize under java.exe.
        # The identical DJL LibTorch build loads in the Python-hosted JVM.
        jpype.startJVM("-Dai.djl.pytorch.num_threads=2", jvmpath=str(jvm), classpath=[str(jar), classes])
        try:
            jpype.JClass("EpsilonMjai").main([str(jar.parent)])
        finally:
            jpype.shutdownJVM()


if __name__ == "__main__":
    main()
