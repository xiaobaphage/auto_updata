from setuptools import setup, find_packages

setup(
    name="auto_updata",
    version="1.0.1",
    author="xiaobaphage",
    author_email="xiaobaphage@outlook.com",
    description="一个自动更新模块，支持检查、下载和安装更新",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/xiaobaphage/auto_updata",
    packages=find_packages(),
    package_dir={"auto_updata": "auto_updata"},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Software Distribution",
    ],
    python_requires=">=3.7",
    install_requires=[
        "httpx>=0.24.0",
        "packaging>=21.0",
        "tqdm>=4.65.0",
        "pathlib>=1.0.1",
    ],
    package_data={
        "auto_updata": ["update_config.json"],
    },
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "auto_updata=auto_updata.main:main",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/xiaobaphage/auto_updata/issues",
        "Source": "https://github.com/xiaobaphage/auto_updata",
        "Documentation": "https://github.com/xiaobaphage/auto_updata/wiki",
    },
)