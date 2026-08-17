from pathlib import Path
from setuptools import find_packages, setup

README = Path(__file__).with_name("README.md").read_text(encoding="utf-8")

setup(
    name="async-github",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["aiohttp>=3.8,<4"],
    python_requires=">=3.8",
    author="Student Developer",
    description="Typed asynchronous GitHub REST API wrapper",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/async-github",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Framework :: AsyncIO",
    ],
)
