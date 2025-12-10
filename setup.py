# setup.py
import setuptools
import platform

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
    package_data={ 'automation': ['pages/assets/*'], },
    include_package_data=True,
    packages=setuptools.find_packages(),
    install_requires=_requirements,
    classifiers=[
        "Programming Language :: Python :: 3.9",
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
