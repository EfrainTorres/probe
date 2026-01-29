"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with sample files."""
    # Create a simple Python file
    (tmp_path / "main.py").write_text(
        '''"""Main module."""


def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"


def goodbye(name: str) -> str:
    """Say goodbye."""
    return f"Goodbye, {name}!"


class Greeter:
    """A greeter class."""

    def __init__(self, prefix: str = "Hi"):
        self.prefix = prefix

    def greet(self, name: str) -> str:
        """Greet someone."""
        return f"{self.prefix}, {name}!"
'''
    )

    # Create a README
    (tmp_path / "README.md").write_text(
        """# Test Project

## Overview

This is a test project.

## Usage

Run the main module.
"""
    )

    # Create a config file
    (tmp_path / "config.yaml").write_text(
        """name: test
version: 1.0.0
settings:
  debug: true
  port: 8080
"""
    )

    return tmp_path


@pytest.fixture
def sample_python_code() -> str:
    """Sample Python code for chunking tests."""
    return '''"""Sample module."""

import os
from pathlib import Path


def simple_function():
    """A simple function."""
    return 42


def function_with_args(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


class SimpleClass:
    """A simple class."""

    def __init__(self, value: int):
        self.value = value

    def get_value(self) -> int:
        """Get the value."""
        return self.value

    def set_value(self, value: int) -> None:
        """Set the value."""
        self.value = value
'''


@pytest.fixture
def sample_markdown() -> str:
    """Sample markdown for chunking tests."""
    return """# Main Title

Introduction paragraph.

## Section One

Content for section one.
More content here.

## Section Two

Content for section two.

### Subsection

Nested content.

## Section Three

Final section.
"""
