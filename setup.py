import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="netcop",
    version="1.0",
    author="Alexey Andriyanov",
    author_email="alanm@bk.ru",
    description="A vendor-agnostic parser of network configs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/andriyanov/netcop",
    packages=["netcop"],
    classifiers=[
        "Programming Language :: Python",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
