#!/usr/bin/env python3
"""Build the optional Clang 18 CFG helper; no automatic downloads or apt installs."""
import argparse, os, subprocess, shutil
from pathlib import Path
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--llvm-dir',required=True,help='LLVM installation prefix, e.g. /usr/lib/llvm-18')
p.add_argument('--build-dir',required=True)
p.add_argument('--output-dir',help='Defaults to the platform runtime/native directory')
a=p.parse_args();prefix=Path(a.llvm_dir).resolve()
out=Path(a.output_dir).resolve() if a.output_dir else root/'runtime'/('windows-x86_64' if os.name=='nt' else 'linux-x86_64')/'native'
platform_name='windows-x86_64' if os.name=='nt' else 'linux-x86_64'
bundled=root/'runtime'/platform_name/'site/cmake/data/bin'/('cmake.exe' if os.name=='nt' else 'cmake')
cmake=str(bundled) if bundled.is_file() else shutil.which('cmake')
if not cmake:raise SystemExit('CMake missing; use full runtime package or install CMake')
subprocess.run([cmake,'-S',str(root/'native'),'-B',str(Path(a.build_dir).resolve()),'-DCMAKE_BUILD_TYPE=Release','-DLLVM_DIR='+str(prefix/'lib/cmake/llvm'),'-DCMAKE_INSTALL_PREFIX='+str(out.parent)],check=True)
subprocess.run([cmake,'--build',str(Path(a.build_dir).resolve()),'--parallel','2'],check=True)
# Copy only after successful compilation; shared LLVM dependencies belong to packaging.
import shutil
out.mkdir(parents=True,exist_ok=True)
name='atlas-semantic.exe' if os.name=='nt' else 'atlas-semantic'
src=Path(a.build_dir)/name
if not src.exists():src=Path(a.build_dir)/'Release'/name
shutil.copy2(src,out/name)
subprocess.run([str(out/name),'--version'],check=True)
print(out/name)
