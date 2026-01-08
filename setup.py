# setup.py
import setuptools
import platform
import os
import shutil
from pathlib import Path

with open("README.md", "r") as fh:
    long_description = fh.read()

try:
    with open("requirements.txt", "r") as fh:
        _requirements = fh.read().splitlines()
except FileNotFoundError:
    _requirements = []

version_ns = {}
with open("version.py") as f:
    exec(f.read(), version_ns)
version = version_ns['__version__']

# Copiar HMI construido a automation/hmi/ antes de empaquetar
hmi_dist_path = Path("hmi/dist")
automation_hmi_path = Path("automation/hmi")

# Limpiar directorio anterior si existe
if automation_hmi_path.exists():
    shutil.rmtree(automation_hmi_path)

# Copiar HMI si existe
if hmi_dist_path.exists() and (hmi_dist_path / "index.html").exists():
    automation_hmi_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(hmi_dist_path, automation_hmi_path)
    print(f"[INFO] HMI copiado a {automation_hmi_path} para empaquetado")

# Configurar package_data
package_data = {
    'automation': ['pages/assets/*']
}

# Agregar archivos del HMI si fueron copiados
if automation_hmi_path.exists():
    hmi_files = []
    for root, dirs, files in os.walk(automation_hmi_path):
        for file in files:
            # Ruta relativa desde automation/hmi
            rel_path = os.path.relpath(os.path.join(root, file), automation_hmi_path)
            hmi_files.append(f'hmi/{rel_path}')
    if hmi_files:
        package_data['automation'].extend(hmi_files)

system_platform = platform.system()
setuptools.setup(
    name="PyAutomationIO",
    version=version,
    author="KnowAI",
    author_email="dev.know.ai@gmail.com",
    description="A python framework to develop automation industrial processes applications and Artificial Intelligence applications for the industrial field",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="GNU AFFERO GENERAL PUBLIC LICENSE",
    url="https://github.com/know-ai/PyAutomation",
    package_data=package_data,
    include_package_data=True,
    packages=setuptools.find_packages(),
    install_requires=_requirements,
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries",
        "Topic :: System :: Logging",
        "Topic :: System :: Monitoring"
    ]
)
