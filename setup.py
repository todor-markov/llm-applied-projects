from setuptools import setup, find_packages

setup(
    name="llm_projects",
    version="0.1.0",
    author="Todor Markov",
    description="A short description of your project",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    url="https://github.com/todor-markov/llm-applied-projects",
    packages=find_packages(),
    python_requires='>=3.6',
    install_requires=[
        # List your project's dependencies here.
        # You can use an external file to manage them.
        "anthropic",
        "python-dotenv",
    ],
)
